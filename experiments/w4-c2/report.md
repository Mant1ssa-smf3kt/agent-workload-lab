# w4-c2 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer d77ffcc4
配置：timing=real · concurrency=2 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260920T233603 | 20260921T002900 | 20260921T012158 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9628 | 0.9626 | 0.9626 | 0.9626 ± 0.0001 | 0.9626 – 0.9628 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9627 | 0.9625 | 0.9625 | 0.9626 ± 0.0001 | 0.9625 – 0.9627 | 0.0% |
| TTFT P50 | 261 ms | 260 ms | 261 ms | 261 ms ± 1 ms | 260 ms – 261 ms | 0.2% |
| TTFT P95 | 549 ms | 545 ms | 537 ms | 544 ms ± 6 ms | 537 ms – 549 ms | 1.2% |
| TTFT P99 | 1242 ms | 1940 ms | 1746 ms | 1643 ms ± 360 ms | 1242 ms – 1940 ms | 21.9% |
| latency P50 | 2547 ms | 2556 ms | 2541 ms | 2548 ms ± 8 ms | 2541 ms – 2556 ms | 0.3% |
| latency P95 | 23994 ms | 23968 ms | 23958 ms | 23973 ms ± 19 ms | 23958 ms – 23994 ms | 0.1% |
| latency P99 | 41085 ms | 41119 ms | 41073 ms | 41092 ms ± 24 ms | 41073 ms – 41119 ms | 0.1% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 3174.2 s | 3174.7 s | 3175.5 s | 3174.8 s ± 0.7 s | 3174.2 s – 3175.5 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
