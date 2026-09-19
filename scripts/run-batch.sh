#!/usr/bin/env bash
# 远端：串行跑一批实验，每个 N 次，跑完自动出报告。写成文件再 nohup，别把命令文本塞进 bash -c
# （pgrep 会匹配到自己）。【需要开卡；由人确认后执行。】
#
#   nohup bash scripts/run-batch.sh 3 w3-control w3-timestamp w3-tools-rotate w3-truncate > /root/autodl-tmp/batch.log 2>&1 &
#
# 前提：serve.sh 已 ready；.sync-commit 存在（指纹带 replayer commit）。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
REPEATS="${1:?usage: run-batch.sh <repeats> <exp>...}"; shift
cd "$ROOT" && source scripts/env.sh
export PATH="/root/miniconda3/bin:$PATH"
log() { printf '{"ts":"%s","batch":"%s","msg":"%s"}\n' "$(date -Is)" "$1" "$2"; }

curl -sf "$SGLANG_HOST:$SGLANG_PORT/v1/models" >/dev/null || { log check "server not reachable at $SGLANG_HOST:$SGLANG_PORT"; exit 2; }
[[ -f .sync-commit ]] || log check "WARNING: .sync-commit missing; replayer commit will be null in fingerprints"

for exp in "$@"; do
  for i in $(seq 1 "$REPEATS"); do
    log "$exp" "run $i/$REPEATS start"
    if ! uv run python -m replay.run "experiments/$exp/config.yaml" > "/root/autodl-tmp/replay-$exp-run$i.log" 2>&1; then
      log "$exp" "run $i FAILED (see replay-$exp-run$i.log); continuing"
    fi
    tail -1 "/root/autodl-tmp/replay-$exp-run$i.log" | cut -c1-300
  done
  uv run python -m analysis.report "$exp" 2>/dev/null && log "$exp" "report written"
done
log done "batch finished"
