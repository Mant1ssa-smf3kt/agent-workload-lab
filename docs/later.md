# later.md

与当前实验不直接相关、以后可能做的东西，记这里。做完的条目删掉，不留「已完成」。

- pi `compat.sendSessionAffinityHeaders`：openai-completions 下可按 session id 发亲和性头。若日后做 hint / 会话亲和调度实验，这是 harness 侧现成的挂点，不用改 pi。W4 已决定不做 hint 实验（decisions 2026-09-21）。
- zai `clear_thinking: false` 会把 `reasoning_content` 写回历史 assistant 消息。Qwen3 chat template 对历史 `reasoning_content` 的渲染规则未单独验证；本项目全部 trace 为 thinking off，不受影响。
- RTX 5090 (Blackwell, sm_120) 与 SGLang 0.5.20 的兼容性未验证；AutoDL 5090 镜像自带 CUDA 12.8。全部实验在 4090 上完成。
- KV 池大小作为变量：`--kv-cache-dtype fp8_e5m2` 池子约翻倍（≈157k），但 4090 + sglang 0.5.20 兼容未验证、dtype 改变 attention kernel、延迟不与 bf16 同表（只比缓存类指标 ~5 h，全套 ~23 h）；`--max-total-tokens N` 能精确设池子但下限 ≈ 54k（最长请求 53.4k），落在 c2 边界上，效应小。均未进 W5（decisions 2026-09-21）。
- **compaction 的摘要 LLM 调用不经过 `before_provider_request`**（trace `20260918T114524` 在 turn 84/85 之间无 `request` 记录，只有 `compaction.usage`）。replayer 按 `compaction.usage` 合成一条等长冷 prefill 并标记 synthetic；若要精确复现，需看 pi 的 compaction 是否走 pi-ai `complete()`、能否用 `session_before_compact` 自己发请求——属于「改 pi 内部」，不做。
- 超时请求的删失分位：当前 nearest-rank 下界法足够；若删失比例上升到影响 P95，应换 Kaplan–Meier 估计而不是继续报下界。
