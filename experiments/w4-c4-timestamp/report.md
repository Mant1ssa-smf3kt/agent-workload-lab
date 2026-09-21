# w4-c4-timestamp · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer d77ffcc4
配置：timing=real · concurrency=4 · transform=system_timestamp · traces=25 · timeout_s=600

| 指标 | 20260920T172535 | 20260920T183503 | 20260920T194429 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.0982 | 0.0982 | 0.0979 | 0.0981 ± 0.0002 | 0.0979 – 0.0982 | 0.2% |
| cache hit rate (excl. synthetic) | 0.0979 | 0.0979 | 0.0976 | 0.0978 ± 0.0002 | 0.0976 – 0.0979 | 0.2% |
| TTFT P50 | 4867 ms | 4867 ms | 4988 ms | 4907 ms ± 70 ms | 4867 ms – 4988 ms | 1.4% |
| TTFT P95 | 18185 ms | 18192 ms | 17806 ms | 18061 ms ± 220 ms | 17806 ms – 18192 ms | 1.2% |
| TTFT P99 | 44579 ms | 44550 ms | 48399 ms | 45842 ms ± 2214 ms | 44550 ms – 48399 ms | 4.8% |
| latency P50 | 10795 ms | 10803 ms | 11076 ms | 10891 ms ± 160 ms | 10795 ms – 11076 ms | 1.5% |
| latency P95 | 50579 ms | 50595 ms | 51703 ms | 50959 ms ± 644 ms | 50579 ms – 51703 ms | 1.3% |
| latency P99 | 92783 ms | 92693 ms | 92793 ms | 92756 ms ± 55 ms | 92693 ms – 92793 ms | 0.1% |
| prompt tokens total | 19492943 | 19492943 | 19492943 | 19492943 ± 0 | 19492943 – 19492943 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 4164.5 s | 4163.3 s | 4173.0 s | 4166.9 s ± 5.3 s | 4163.3 s – 4173.0 s | 0.1% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
