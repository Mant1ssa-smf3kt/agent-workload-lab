# later.md

工作时段冒出来的、与当前实验不直接相关的东西，记这里，不展开（CLAUDE.md §12）。

- pi `compat.sendSessionAffinityHeaders`：openai-completions 下可按 session id 发亲和性头。W4 若做 hint 实验，这是 harness 侧现成的挂点，不用改 pi。
- zai `clear_thinking: false` 会把 `reasoning_content` 写回历史 assistant 消息。Qwen3 chat template 对历史 `reasoning_content` 的渲染规则要在 W2 replayer 做 payload 归一化时确认。
- RTX 5090 (Blackwell, sm_120) 与 SGLang 0.5.20 的兼容性未验证；AutoDL 5090 镜像自带 CUDA 12.8。若 4090 可租则优先 4090，减少一个变量。
- `--kv-cache-dtype fp8_e5m2` 能把 KV 容量翻倍，但改变了缓存行为本身；只作为 W4 的独立变量，不进基线。
- **compaction 的摘要 LLM 调用不经过 `before_provider_request`**（trace `20260918T114524` 在 turn 84/85 之间无 `request` 记录，只有 `compaction.usage = {input 18878, output 626}` 与 11.7 s 空档）。extension 拿不到它的 payload。W2 replayer 需按 `compaction.usage` 合成一条等长的冷 prefill 请求并显式标记为合成；若要精确复现，得看 pi 的 compaction 是否走 pi-ai `complete()`、能否用 `session_before_compact` 自己发请求替代——那属于「改 pi 内部」范畴，先不做。
- sglang ≥ 0.5.12 全部是 CUDA 13 栈（PyPI 元数据：torch 2.11/2.13 cu13、flashinfer[cu13]、cuda-python≥13），宿主机驱动 ≥ 580。AutoDL 4090 宿主机若驱动只到 CUDA 12.x，退到 0.5.10（torch 2.9.1 cu128）。已写进 remote.md 与 setup.sh 的驱动检查。
- 合成 compaction 请求应保留 `tools`：Qwen3 chat template 把 tools 渲染在 system 段开头之后，去掉 tools 会让整条前缀从 ~3.7k token 起失配（baseline-c1 实测该请求命中 0.197）。改 `replay/trajectory.py::synthesize_compaction_payload`，作为 W3 前的保真修正，记 decisions。
- `metrics.key_metrics` 对带多组 label 的 counter（如 `prompt_tokens_total{is_streaming=…}`）只取第一组；应对 `*_total` 求和。
- `warmup_requests` 语义应改为「第一条轨迹的前 N 步」而非「全局最先发出的 N 条」，否则不同并发下剔除的请求不同（c1 vs c3 的 prompt tokens total 差 2740）。
