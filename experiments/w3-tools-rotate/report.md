# w3-tools-rotate · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 2ce925b8
配置：timing=compressed · concurrency=1 · transform=tools_rotate · traces=25 · timeout_s=600

| 指标 | 20260919T204655 | 20260919T223104 | 20260920T001512 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.3150 | 0.3150 | 0.3150 | 0.3150 ± 0.0000 | 0.3150 – 0.3150 | 0.0% |
| cache hit rate (excl. synthetic) | 0.3150 | 0.3150 | 0.3150 | 0.3150 ± 0.0000 | 0.3150 – 0.3150 | 0.0% |
| TTFT P50 | 1232 ms | 1231 ms | 1228 ms | 1231 ms ± 2 ms | 1228 ms – 1232 ms | 0.2% |
| TTFT P95 | 5950 ms | 5955 ms | 5949 ms | 5951 ms ± 3 ms | 5949 ms – 5955 ms | 0.1% |
| TTFT P99 | 7746 ms | 7655 ms | 7651 ms | 7684 ms ± 54 ms | 7651 ms – 7746 ms | 0.7% |
| latency P50 | 5252 ms | 5228 ms | 5230 ms | 5237 ms ± 14 ms | 5228 ms – 5252 ms | 0.3% |
| latency P95 | 24082 ms | 24072 ms | 24075 ms | 24076 ms ± 6 ms | 24072 ms – 24082 ms | 0.0% |
| latency P99 | 41111 ms | 41150 ms | 41124 ms | 41128 ms ± 20 ms | 41111 ms – 41150 ms | 0.0% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | — | — | — | — | — | — |
| wall | 6246.0 s | 6244.2 s | 6240.9 s | 6243.7 s ± 2.6 s | 6240.9 s – 6246.0 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
