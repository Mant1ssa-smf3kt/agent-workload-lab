#!/usr/bin/env bash
# End-to-end smoke test: real pi + this extension + a fake OpenAI-compatible
# streaming server. No credentials, no cost, no GPU. Verifies that jiti loads
# the extension, the hooks fire in the real order, and a trace lands on disk.
#
#   bash extension/smoke/run.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT="$HERE/../src/index.ts"
WORK="$(mktemp -d)"
trap 'kill "${SERVER_PID:-}" 2>/dev/null || true; rm -rf "$WORK"' EXIT

mkdir -p "$WORK/repo" "$WORK/traces"
echo "hello from smoke repo" > "$WORK/repo/README.md"

node "$HERE/fake-openai.mjs" 2> "$WORK/server.log" &
SERVER_PID=$!
curl -sf --retry 30 --retry-connrefused --retry-all-errors --retry-delay 1 \
    http://127.0.0.1:18080/v1/models >/dev/null

( cd "$WORK/repo" && pi -e "$EXT" -e "$HERE/fake-provider.ts" \
    --trace-dir "$WORK/traces" --model fake/fake-1 --no-session -p "read the readme" < /dev/null )

echo "--- server saw:"; cat "$WORK/server.log"
TRACE="$(ls "$WORK/traces"/*.jsonl)"
echo "--- trace: $TRACE"
node -e '
const fs = require("node:fs");
const recs = fs.readFileSync(process.argv[1], "utf8").trim().split("\n").map(JSON.parse);
const types = recs.map(r => r.type);
console.log(types.join(" "));
const want = ["header","user_prompt","agent_start","turn_start","context","request","tool","turn_end","turn_start","context","request","turn_end","agent_end","agent_settled","shutdown"];
if (JSON.stringify(types) !== JSON.stringify(want)) { console.error("UNEXPECTED RECORD SEQUENCE"); process.exit(1); }
const reqs = recs.filter(r => r.type === "request");
for (const r of reqs) {
  const ok = r.outcome === "done" && r.http_status === 200 && r.t_first_delta > r.t_request && r.usage && r.payload && r.payload.messages;
  if (!ok) { console.error("BAD REQUEST RECORD", JSON.stringify({...r, payload: "…"})); process.exit(1); }
}
if (recs[0].schema !== 1 || recs[0].pi_version === undefined) { console.error("BAD HEADER"); process.exit(1); }
console.log(`OK: ${reqs.length} requests, ttft ${reqs.map(r => r.t_first_delta - r.t_request + "ms").join(", ")}`);
' "$TRACE"
