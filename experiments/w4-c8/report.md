# w4-c8 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer d77ffcc4
配置：timing=real · concurrency=8 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260920T205405 | 20260920T214812 | 20260920T224317 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.5151 | 0.5316 | 0.5461 | 0.5309 ± 0.0155 | 0.5151 – 0.5461 | 2.9% |
| cache hit rate (excl. synthetic) | 0.5145 | 0.5311 | 0.5455 | 0.5303 ± 0.0155 | 0.5145 – 0.5455 | 2.9% |
| TTFT P50 | 4830 ms | 4825 ms | 4368 ms | 4674 ms ± 265 ms | 4368 ms – 4830 ms | 5.7% |
| TTFT P95 | 36355 ms | 40673 ms | 34284 ms | 37104 ms ± 3260 ms | 34284 ms – 40673 ms | 8.8% |
| TTFT P99 | 185823 ms | 222013 ms | 262605 ms | 223480 ms ± 38412 ms | 185823 ms – 262605 ms | 17.2% |
| latency P50 | 10995 ms | 10650 ms | 10037 ms | 10561 ms ± 485 ms | 10037 ms – 10995 ms | 4.6% |
| latency P95 | 73330 ms | 68751 ms | 69376 ms | 70486 ms ± 2483 ms | 68751 ms – 73330 ms | 3.5% |
| latency P99 | 200237 ms | 228577 ms | 264962 ms | 231259 ms ± 32446 ms | 200237 ms – 264962 ms | 14.0% |
| prompt tokens total | 19364720 | 19403430 | 19358869 | 19375673 ± 24216 | 19358869 – 19403430 | 0.1% |
| requests | 833 | 835 | 832 | 833 ± 2 | 832 – 835 | 0.2% |
| errors | 4 | 2 | 5 | 4 ± 2 | 2 – 5 | 41.7% |
| timeouts (censored) | 4 | 2 | 5 | 4 ± 2 | 2 – 5 | 41.7% |
| wall | 3244.1 s | 3302.1 s | 3163.5 s | 3236.6 s ± 69.6 s | 3163.5 s – 3302.1 s | 2.1% |

**判定**：3 次以上同配置重跑，指纹一致，11 个请求超时，已按右删失计入 TTFT/latency 分位（标 ≥ 的为下界）。 可用于对照。
