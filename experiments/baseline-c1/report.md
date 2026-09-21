# baseline-c1 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer TBD
配置：timing=real · concurrency=1 · transform=identity · traces=3 · timeout_s=600

| 指标 | 20260918T222305 | 20260918T224449 | 20260919T083248 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9688 | 0.9696 | 0.9688 | 0.9691 ± 0.0005 | 0.9688 – 0.9696 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9717 | 0.9725 | 0.9717 | 0.9720 ± 0.0005 | 0.9717 – 0.9725 | 0.0% |
| TTFT P50 | 250 ms | 246 ms | 246 ms | 247 ms ± 2 ms | 246 ms – 250 ms | 0.9% |
| TTFT P95 | 558 ms | 560 ms | 529 ms | 549 ms ± 17 ms | 529 ms – 560 ms | 3.1% |
| TTFT P99 | 1739 ms | 1727 ms | 1591 ms | 1686 ms ± 82 ms | 1591 ms – 1739 ms | 4.9% |
| latency P50 | 2253 ms | 2245 ms | 2226 ms | 2241 ms ± 14 ms | 2226 ms – 2253 ms | 0.6% |
| latency P95 | 23036 ms | 23095 ms | 22608 ms | 22913 ms ± 266 ms | 22608 ms – 23095 ms | 1.2% |
| latency P99 | 36637 ms | 36746 ms | 35884 ms | 36422 ms ± 470 ms | 35884 ms – 36746 ms | 1.3% |
| prompt tokens total | 4991988 | 4991988 | 4991988 | 4991988 ± 0 | 4991988 – 4991988 | 0.0% |
| requests | 171 | 171 | 171 | 171 ± 0 | 171 – 171 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | — | — | — | — | — | — |
| wall | 1266.3 s | 1265.8 s | 1248.1 s | 1260.1 s ± 10.4 s | 1248.1 s – 1266.3 s | 0.8% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
