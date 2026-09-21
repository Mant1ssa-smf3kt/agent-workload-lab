# agent-workload-lab

*English · [中文](README.zh-CN.md)*

Measures how a coding agent's **context-assembly strategy** on the harness side changes **prefix-cache and scheduling behaviour** on the LLM serving side. Real [pi](https://github.com/badlogic/pi-mono) coding sessions are recorded once against a cloud model, then replayed as load against a local SGLang instance under controlled concurrency, with radix-cache hits, TTFT, queue depth and tail latency collected per request.

> A harness that writes the current time at the end of the system prompt drops the radix-cache hit rate from **0.9633 to 0.1059**, raises single-turn P95 latency by **7.7 %** and TTFT P95 by **1078.7 %** (507 → 5971 ms) at single concurrency; append-only assembly restores 0.9633. With four sessions in flight the same change costs **+36.7 %** on turn P95 and **+1046 %** on TTFT P50.

All numbers: one RTX 4090 · SGLang 0.5.20 · Qwen3-8B-FP8 · 25 recorded trajectories (837 requests per replay) · every configuration replayed 3× with variance reported. Sources: [`experiments/*/report.md`](experiments) and [`docs/findings.md`](docs/findings.md).

## Results

### Context transforms at single concurrency (W3)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/w3-transforms-dark.png">
  <img alt="Cache hit rate, TTFT P95 and turn-latency P95 for four context transforms" src="docs/figures/w3-transforms.png">
</picture>

| transform (vs append-only control) | cache hit | TTFT P95 | turn latency P95 | prompt tokens |
|---|---|---|---|---|
| append-only (control) | 0.9633 | 507 ms | 22.8 s | 19.47 M |
| `system_timestamp` — clock at the end of the system prompt | **0.1059** | **5971 ms** (+1079 %) | 24.6 s (+7.7 %) | +0.1 % |
| `tools_rotate` — tool list rotated by one each request | 0.3150 | 5951 ms (+1074 %) | 24.1 s (+5.5 %) | ±0 |
| `truncate_tool_results` — old tool outputs clipped | 0.9102 | 695 ms (+37 %) | **21.2 s (−7.1 %)** | **−29.2 %** |

### Concurrency sweep with real inter-turn timing (W4)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/w4-concurrency-dark.png">
  <img alt="Cache hit rate, evicted tokens, TTFT P95 and turn-latency P95 against concurrency" src="docs/figures/w4-concurrency.png">
</picture>

| sessions in flight | cache hit | TTFT P50 / P95 / P99 | turn latency P50 / P95 / P99 | evicted tokens / run | queue non-empty | timeouts (≥ 600 s) | wall |
|---|---|---|---|---|---|---|---|
| 1 | 0.9633 | 0.24 / 0.51 / 0.86 s | 2.4 / 22.7 / 39.8 s | 0.96 M | 0 % | 0 | 5958 s |
| 2 | 0.9626 | 0.26 / 0.54 / 1.6 s | 2.5 / 24.0 / 41.1 s | 0.97 M | 1.6 % | 0 | 3175 s |
| 4 | 0.7520 | 0.43 / **13.1** / 27.8 s | 6.1 / 37.3 / 64.8 s | 5.1 M | 49 % | 0 | 2792 s |
| 8 | 0.5309 | 4.7 / 37.1 / 223 s | 10.6 / 70.5 / 231 s | 9.3 M | 82 % | **11** | **3237 s** |
| 4 + `system_timestamp` | **0.0981** | 4.9 / 18.1 / 45.8 s | 10.9 / 51.0 / 92.8 s | **17.8 M** | 52 % | 0 | 4167 s |

Timed-out requests are kept in the percentiles as right-censored lower bounds, not dropped ([decision](docs/decisions.md)). c=8 P99 has CV 14–17 %; everything else ≤ 4.8 %.

### What the data says that is not obvious

Full write-up with sources in [`docs/findings.md`](docs/findings.md).

1. **Past the cache-fitting concurrency, more concurrency reduces throughput.** c=8 takes 16 % longer wall time than c=4 for the same 19.4 M prompt tokens, re-prefills 9.3 M evicted tokens and drops 11 requests.
2. **All memory pressure is absorbed by prefix eviction; retraction never triggers.** `num_retracted_reqs` is 0 in all 15 runs. Agent turns emit ~114 output tokens on ~21 k-token prompts, so the KV pool is full of *idle sessions' cached prefixes*, and the scheduler always has something to evict. At c ≥ 4, evicted tokens ≈ missed tokens: every eviction is a live session paying a cold prefill later.
3. **Hit rate is a poor predictor of latency.** −5 points of hit rate came with −7 % turn P95 (truncation); −21 points came with +2488 % TTFT P95 (queueing); the next −65 points added only +38 %. Report miss *volume* and queue occupancy, not the hit percentage.
4. **Truncating old tool results improves turn latency through faster decode, not cheaper prefill** — TTFT got worse (+37 %) while turn P95 got better (−7 %) with identical output lengths.
5. **Run-to-run variance of the hit rate is itself a signal.** It is byte-identical across repeats at c=1 (std 0.0000) and drifts once eviction starts (0.0054 at c=4, 0.0155 at c=8).
6. **Harness changes can be evaluated offline for single-tenant hit rate** — a chat-template-aware longest-common-prefix predicted the direction of all three transforms — **but not for their cost under concurrency**, which went from +7.7 % to +36.7 % on turn P95.
7. *(mechanism inferred)* Under longest-prefix-match scheduling the starved requests are exactly the ones with the least cacheable prefix: a long session whose prefix was evicted during a tool call, and brand-new sessions — one 1675-token cold-start request waited more than 10 minutes.
8. *(inferred)* The cliff sits where `concurrent sessions × context length` exceeds the KV pool (78 k tokens here, ~25 k per session): fine at 2, broken at 4.

## What is in the repository

```
pi + extension/  ──record──▶  traces/*.jsonl  ──replay/──▶  SGLang on one GPU
                                   │                            │
                            analysis/profile           metrics/ + per-run artifact
                            (workload profile)         experiments/<name>/out/<run>/
                                                                │
                                                       analysis/report · analysis/plot
```

| Directory | Contents |
|---|---|
| `extension/` | pi extension (TypeScript) that records every provider request verbatim with timing points, tool durations and turn boundaries. Observe-only. |
| `replay/` | Replayer: trajectory → normalised payload sequence → replayed to an OpenAI-compatible endpoint at a chosen concurrency and timing mode; writes a self-describing artifact per run (config, fingerprint, plan, per-request log, metrics snapshots, summary). Includes the context transforms under test. |
| `metrics/` | SGLang `/metrics` sampler. |
| `analysis/` | Workload profile, variance/comparison reports (refuse to compare mismatched fingerprints or more than one changed variable — a changed SGLang launch flag counts as a variable), figures, and `estimate` — the GPU-free first gate: every request rendered through the served model's real chat template and tokenizer, hit rate = token-level longest common prefix with what the server has seen (calibrated to the measured runs within 0.0007 at c=1). |
| `experiments/` | One directory per experiment: `config.yaml` + generated `report.md` / `compare-*.md` / `estimate.md`. Raw `out/` is not committed. `w5-*` are planned, not yet run. |
| `scripts/` | Remote (AutoDL) setup, SGLang launch with fingerprinting, rsync, recording helpers. |
| `docs/` | [`findings.md`](docs/findings.md) conclusions · [`experiments.md`](docs/experiments.md) run log incl. negative results · [`decisions.md`](docs/decisions.md) metric definitions and trade-offs · [`recording.md`](docs/recording.md) / [`remote.md`](docs/remote.md) runbooks · [`figures/`](docs/figures) |

Metric definitions (fixed for the whole project; changes are logged in `decisions.md`):

- **prefix-cache hit rate** = cached prefill tokens / total prefill tokens, aggregated over requests (from `usage.prompt_tokens_details.cached_tokens`, SGLang `--enable-cache-report`).
- **TTFT** = request sent → first content token, including queueing. **Turn latency** = request sent → stream finished.
- Tails are always P50 / P95 / P99; client-timeout requests enter as right-censored lower bounds.

## Reproducing

Trajectories are **not** included: they contain source files of third-party repositories and model outputs. Their sha256 and shape (requests, prompt sizes, tool mix) are in [`experiments/profile/meta.json`](experiments/profile/meta.json) and [`profile.md`](experiments/profile/profile.md). To reproduce you record your own; the pipeline is otherwise fully scripted.

Local (no GPU):

```bash
uv sync && just test && just lint                 # Python 3.12 + uv; Node 20+ for extension tests
bash scripts/record.sh <repo> <case-name>         # record one trajectory with pi (your own model/API key)
just profile                                      # workload profile → experiments/profile/out/
just replay-dry w4-c4                             # build the replay plan without a server
just estimate w3-timestamp w3-control             # first gate: hit-rate estimate through the real chat template + tokenizer
```

Remote (one 24 GB GPU; the project used AutoDL RTX 4090, see [`docs/remote.md`](docs/remote.md)):

```bash
cp scripts/remote.env.example scripts/remote.env  # SSH host/port
bash scripts/sync.sh --traces                     # code + traces → remote
ssh … 'bash scripts/setup.sh'                     # sglang 0.5.20 venv + Qwen3-8B-FP8 weights (idempotent)
ssh … 'bash scripts/serve.sh'                     # launches SGLang and writes the environment fingerprint
ssh … 'nohup bash scripts/run-batch.sh 3 w4-c1 w4-c2 w4-c4 w4-c8 w4-c4-timestamp &'
bash scripts/sync.sh --pull w4-c4                 # artifacts → local
just report w4-c4 && just compare w4-c4 w4-c1 && just plot
```

Every artifact carries an environment fingerprint (GPU, driver, SGLang version and launch args, model checksum, pi version, replayer commit, trace checksums); reports refuse to put runs with different fingerprints in one table. Measured replay time across the 30 committed runs sums to ≈ 36 GPU-hours (`wall` rows in `experiments/*/report.md`), excluding setup, model load and warm-up.

## Scope and limitations

- One GPU, one model, one serving stack, one harness. Absolute numbers do not transfer; the qualitative findings depend on the workload shape (long prompts, short outputs, gaps between turns) and should, but that is untested.
- Transform experiments (W3) use compressed timing, the concurrency sweep (W4) real timing; the two tables are never compared directly. At c=1 the two modes agree within 1.7 % on every percentile.
- Task success is deliberately out of scope: the replay model is a small local model and only the token sequence and timing of the recorded sessions are reproduced.
- Not done: c=3, a longer client timeout at c=8, FCFS-vs-LPM scheduling, KV-cache FP8. See [`docs/later.md`](docs/later.md).

Working conventions for anyone (human or agent) contributing are in [CLAUDE.md](CLAUDE.md). License: [MIT](LICENSE).
