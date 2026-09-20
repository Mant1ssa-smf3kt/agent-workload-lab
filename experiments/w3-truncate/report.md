# w3-truncate · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 2ce925b8
配置：timing=compressed · concurrency=1 · transform=truncate_tool_results · traces=25

| 指标 | 20260920T015916 | 20260920T031252 | 20260920T042627 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9102 | 0.9102 | 0.9102 | 0.9102 ± 0.0000 | 0.9102 – 0.9102 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9101 | 0.9101 | 0.9101 | 0.9101 ± 0.0000 | 0.9101 – 0.9101 | 0.0% |
| TTFT P50 | 241 ms | 239 ms | 240 ms | 240 ms ± 1 ms | 239 ms – 241 ms | 0.3% |
| TTFT P95 | 701 ms | 691 ms | 694 ms | 695 ms ± 5 ms | 691 ms – 701 ms | 0.8% |
| TTFT P99 | 1002 ms | 1007 ms | 1008 ms | 1006 ms ± 3 ms | 1002 ms – 1008 ms | 0.3% |
| latency P50 | 2265 ms | 2267 ms | 2268 ms | 2267 ms ± 2 ms | 2265 ms – 2268 ms | 0.1% |
| latency P95 | 21183 ms | 21208 ms | 21193 ms | 21194 ms ± 13 ms | 21183 ms – 21208 ms | 0.1% |
| latency P99 | 39235 ms | 39225 ms | 39231 ms | 39231 ms ± 5 ms | 39225 ms – 39235 ms | 0.0% |
| prompt tokens total | 13776632 | 13776632 | 13776632 | 13776632 ± 0 | 13776632 – 13776632 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 4412.5 s | 4412.5 s | 4412.9 s | 4412.6 s ± 0.2 s | 4412.5 s – 4412.9 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
