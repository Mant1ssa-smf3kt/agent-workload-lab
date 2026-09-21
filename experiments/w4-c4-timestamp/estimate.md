# w4-c4-timestamp · 第一道门估计（单租户、无驱逐、不含延迟）

模型 / tokenizer：Qwen/Qwen3-8B-FP8（tokenizer.json aeb13307a71a… · chat_template a55ee1b16601… · chat_template_kwargs {"enable_thinking": false}）· traces 25 · steps 839（合成 2，warmup 2 不计）· transform system_timestamp {} · analysis commit d283d498

> config 的 concurrency=4；本估计按 c=1、不驱逐算，并发下的驱逐与排队只能上 GPU（docs/findings.md §6）。

| 组 | cache hit（估计） | 上界（缓存无限） | 每请求命中 P50 / P95 / P99 | 命中 < 0.5 的请求 | prompt tok 总 | n |
|---|---|---|---|---|---|---|
| w4-c4-timestamp | 0.1064 | 0.1064 | 0.107 / 0.360 / 0.586 | 98.2% | 19.40M | 837 |
| w4-c4-timestamp（不含合成） | 0.1062 | 0.1062 | 0.107 / 0.353 / 0.572 | 98.3% | 19.38M | 835 |
| w4-c4（对照） | 0.9633 | 0.9633 | 0.979 / 0.996 / 0.998 | 4.8% | 19.38M | 837 |
| Δ（w4-c4-timestamp − w4-c4） | -0.8569 (-89.0%) | | | | +20,925 | |

配置差异：
- `transform`: {"name": "system_timestamp", "params": {}} → {"name": "identity", "params": {}}

估计口径：每个请求的命中 token = 经服务端 chat template 渲染、真 tokenizer 分词后，与「同一轨迹的上一请求」或「更早轨迹的首请求」的最长公共前缀（c=1 派发顺序、不驱逐）；命中率 = Σ命中 / Σprompt（§5）。「上界」另把同一轨迹全部更早请求算作候选（缓存无限大）；有周期的改写（tools_rotate）实测落在两者之间。不估计 TTFT / 单轮延迟。校准与适用边界见 docs/decisions.md 2026-09-21。

跳过的 trace：
- 20260918T112808.996_01a0b446-1cf4-755d-81cc-42bc16e7447c.jsonl: 0 requests < min_requests 1
