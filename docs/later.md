# later.md

工作时段冒出来的、与当前实验不直接相关的东西，记这里，不展开（CLAUDE.md §12）。

- pi `compat.sendSessionAffinityHeaders`：openai-completions 下可按 session id 发亲和性头。W4 若做 hint 实验，这是 harness 侧现成的挂点，不用改 pi。
- zai `clear_thinking: false` 会把 `reasoning_content` 写回历史 assistant 消息。Qwen3 chat template 对历史 `reasoning_content` 的渲染规则要在 W2 replayer 做 payload 归一化时确认。
- RTX 5090 (Blackwell, sm_120) 与 SGLang 0.5.20 的兼容性未验证；AutoDL 5090 镜像自带 CUDA 12.8。若 4090 可租则优先 4090，减少一个变量。
- `--kv-cache-dtype fp8_e5m2` 能把 KV 容量翻倍，但改变了缓存行为本身；只作为 W4 的独立变量，不进基线。
