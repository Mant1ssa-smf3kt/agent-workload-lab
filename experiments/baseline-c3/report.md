# baseline-c3 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer TBD
配置：timing=real · concurrency=3 · transform=identity · traces=3

| 指标 | 20260919T085653 | 20260919T091059 | 20260919T092505 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9697 | 0.9697 | 0.9697 | 0.9697 ± 0.0000 | 0.9697 – 0.9697 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9726 | 0.9726 | 0.9726 | 0.9726 ± 0.0000 | 0.9726 – 0.9726 | 0.0% |
| TTFT P50 | 269 ms | 268 ms | 266 ms | 268 ms ± 1 ms | 266 ms – 269 ms | 0.5% |
| TTFT P95 | 547 ms | 585 ms | 557 ms | 563 ms ± 19 ms | 547 ms – 585 ms | 3.4% |
| TTFT P99 | 1592 ms | 1574 ms | 1595 ms | 1587 ms ± 11 ms | 1574 ms – 1595 ms | 0.7% |
| latency P50 | 2340 ms | 2338 ms | 2331 ms | 2336 ms ± 5 ms | 2331 ms – 2340 ms | 0.2% |
| latency P95 | 23268 ms | 23255 ms | 23268 ms | 23263 ms ± 8 ms | 23255 ms – 23268 ms | 0.0% |
| latency P99 | 40976 ms | 41035 ms | 41083 ms | 41031 ms ± 54 ms | 40976 ms – 41083 ms | 0.1% |
| prompt tokens total | 4989248 | 4989248 | 4989248 | 4989248 ± 0 | 4989248 – 4989248 | 0.0% |
| requests | 171 | 171 | 171 | 171 ± 0 | 171 – 171 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 844.9 s | 845.0 s | 845.2 s | 845.0 s ± 0.2 s | 844.9 s – 845.2 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
