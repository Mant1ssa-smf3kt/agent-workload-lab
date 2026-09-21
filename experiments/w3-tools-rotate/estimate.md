# w3-tools-rotate · 第一道门估计（单租户、无驱逐、不含延迟）

模型 / tokenizer：Qwen/Qwen3-8B-FP8（tokenizer.json aeb13307a71a… · chat_template a55ee1b16601… · chat_template_kwargs {"enable_thinking": false}）· traces 25 · steps 839（合成 2，warmup 2 不计）· transform tools_rotate {} · analysis commit d283d498

| 组 | cache hit（估计） | 上界（缓存无限） | 每请求命中 P50 / P95 / P99 | 命中 < 0.5 的请求 | prompt tok 总 | n |
|---|---|---|---|---|---|---|
| w3-tools-rotate | 0.1078 | 0.8657 | 0.109 / 0.364 / 0.593 | 98.1% | 19.38M | 837 |
| w3-tools-rotate（不含合成） | 0.1075 | 0.8655 | 0.108 / 0.356 / 0.579 | 98.2% | 19.36M | 835 |
| w3-control（对照） | 0.9633 | 0.9633 | 0.979 / 0.996 / 0.998 | 4.8% | 19.38M | 837 |
| Δ（w3-tools-rotate − w3-control） | -0.8556 (-88.8%) | | | | +0 | |

配置差异：
- `transform`: {"name": "tools_rotate", "params": {}} → {"name": "identity", "params": {}}

估计口径：每个请求的命中 token = 经服务端 chat template 渲染、真 tokenizer 分词后，与「同一轨迹的上一请求」或「更早轨迹的首请求」的最长公共前缀（c=1 派发顺序、不驱逐）；命中率 = Σ命中 / Σprompt（§5）。「上界」另把同一轨迹全部更早请求算作候选（缓存无限大）；有周期的改写（tools_rotate）实测落在两者之间。不估计 TTFT / 单轮延迟。校准与适用边界见 docs/decisions.md 2026-09-21。

跳过的 trace：
- 20260918T112808.996_01a0b446-1cf4-755d-81cc-42bc16e7447c.jsonl: 0 requests < min_requests 1
