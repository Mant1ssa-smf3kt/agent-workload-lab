# baseline-c1 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer TBD
配置：timing=real · concurrency=1 · transform=identity · traces=3

| 指标 | 20260918T222305 | 20260918T224449 | mean ± std | min – max | CV |
|---|---|---|---|---|---|
| cache hit rate | 0.9688 | 0.9696 | 0.9692 ± 0.0006 | 0.9688 – 0.9696 | 0.1% |
| cache hit rate (excl. synthetic) | 0.9717 | 0.9725 | 0.9721 ± 0.0006 | 0.9717 – 0.9725 | 0.1% |
| TTFT P50 | 250 ms | 246 ms | 248 ms ± 3 ms | 246 ms – 250 ms | 1.2% |
| TTFT P95 | 558 ms | 560 ms | 559 ms ± 2 ms | 558 ms – 560 ms | 0.3% |
| TTFT P99 | 1739 ms | 1727 ms | 1733 ms ± 8 ms | 1727 ms – 1739 ms | 0.5% |
| latency P50 | 2253 ms | 2245 ms | 2249 ms ± 5 ms | 2245 ms – 2253 ms | 0.2% |
| latency P95 | 23036 ms | 23095 ms | 23066 ms ± 42 ms | 23036 ms – 23095 ms | 0.2% |
| latency P99 | 36637 ms | 36746 ms | 36692 ms ± 78 ms | 36637 ms – 36746 ms | 0.2% |
| prompt tokens total | 4991988 | 4991988 | 4991988 ± 0 | 4991988 – 4991988 | 0.0% |
| requests | 171 | 171 | 171 ± 0 | 171 – 171 | 0.0% |
| errors | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 1266.3 s | 1265.8 s | 1266.0 s ± 0.3 s | 1265.8 s – 1266.3 s | 0.0% |

**判定**：只有 2 次 run，方差未确认（需要 ≥ 3 次同配置重跑）。
