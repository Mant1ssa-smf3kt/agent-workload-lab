# pi-trace-recorder

pi extension that records a coding-agent session as a replayable **trajectory**:
the exact provider payload of every LLM request, per-request timing points,
tool execution timing, and turn/run boundaries. Output is one JSONL file per
pi session.

It **observes only**. Every handler returns `undefined`; nothing pi sends or
stores is changed. The two harness intercept points named in CLAUDE.md map to:

| Intercept point | pi hook(s) | Record |
|---|---|---|
| context assembly | `context` | `context` — per-message sha256/size digest of pi's `AgentMessage[]` |
| model request | `before_provider_request` → `after_provider_response` → `message_update` → `message_end` | `request` — verbatim payload + `t_request / t_response / t_first_delta / t_first_content / t_end` + usage |

Lifecycle observers (`agent_*`, `turn_*`, `tool_execution_*`, `session_compact*`, `model_select`, `session_*`) add the framing records.

## Usage

```bash
# one-off
pi -e /path/to/agent-workload-lab/extension/src/index.ts

# or permanently, in ~/.pi/agent/settings.json
{ "extensions": ["/path/to/agent-workload-lab/extension/src/index.ts"] }
```

Trace directory, first hit wins:

1. `--trace-dir <path>` CLI flag
2. `AWL_TRACE_DIR` environment variable
3. `<repo>/traces/` (relative to this file; `traces/` is git-ignored)

The footer shows `rec → <file>` while recording. Recording failures are
printed to stderr and disable the recorder; they never break the session.

## File format

Schema is defined in [`src/schema.ts`](src/schema.ts) (`TRACE_SCHEMA_VERSION`).
Record sequence for one run with one tool call:

```
header user_prompt agent_start
  turn_start context request tool turn_end
  turn_start context request turn_end
agent_end agent_settled shutdown
```

Facts about pi 0.85.1 the recorder relies on (verified by `smoke/run.sh`):

- `before_agent_start` fires **before** `agent_start`; `user_prompt.run` is therefore the run about to start.
- `turnIndex` resets to 0 at every `agent_start`; `run` and `req` are the recorder's own global counters.
- `before_provider_request` fires once per stream. Transport-level retries inside pi-ai do **not** re-fire it; an agent-level retry starts a new stream, and the abandoned one is closed as `outcome: "superseded"`.
- The system prompt is not in `context.messages`; it is `payload.messages[0]` (openai-completions) or `payload.system` (anthropic-messages).
- `usage.cacheRead` is what the provider reported (`prompt_tokens_details.cached_tokens` for OpenAI-compatible servers, including SGLang).

All `t*` fields are `Date.now()` ms from one clock; `seq` breaks ties.
`request.t` and `tool.t` equal their start time, not their write time.

## Development

```bash
npm install          # pins @earendil-works/pi-coding-agent@0.85.1 for types
npm test             # unit tests: pure state machine + fake ExtensionAPI wiring
npm run typecheck
npm run smoke        # real pi + fake OpenAI-compatible server, no credentials/cost
```

`smoke/run.sh` is the only test that exercises real pi. Re-run it after any
pi upgrade; if the record sequence changes, bump `TRACE_SCHEMA_VERSION` and
note it in `docs/decisions.md`.

## Layout

```
src/index.ts     pi wiring: hooks → recorder, trace-dir resolution, fingerprint
src/recorder.ts  TraceRecorder: pure state machine, no pi imports, injectable clock
src/schema.ts    record types + schema version
src/digest.ts    stable JSON + sha256 helpers
src/sink.ts      JsonlFileSink (sync append, fail-safe) / MemorySink (tests)
smoke/           fake OpenAI streaming server + fake provider + runner
```
