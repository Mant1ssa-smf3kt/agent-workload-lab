# w3-control · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 2ce925b8
配置：timing=compressed · concurrency=1 · transform=identity · traces=25

| 指标 | 20260919T112440 | 20260919T124144 | 20260919T135851 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9633 | 0.9633 | 0.9633 | 0.9633 ± 0.0000 | 0.9633 – 0.9633 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9633 | 0.9633 | 0.9633 | 0.9633 ± 0.0000 | 0.9633 – 0.9633 | 0.0% |
| TTFT P50 | 236 ms | 236 ms | 235 ms | 236 ms ± 1 ms | 235 ms – 236 ms | 0.2% |
| TTFT P95 | 502 ms | 511 ms | 507 ms | 507 ms ± 5 ms | 502 ms – 511 ms | 0.9% |
| TTFT P99 | 852 ms | 851 ms | 852 ms | 852 ms ± 0 ms | 851 ms – 852 ms | 0.0% |
| latency P50 | 2355 ms | 2355 ms | 2347 ms | 2352 ms ± 5 ms | 2347 ms – 2355 ms | 0.2% |
| latency P95 | 22790 ms | 22811 ms | 22838 ms | 22813 ms ± 24 ms | 22790 ms – 22838 ms | 0.1% |
| latency P99 | 39830 ms | 39852 ms | 39844 ms | 39842 ms ± 11 ms | 39830 ms – 39852 ms | 0.0% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 4620.9 s | 4624.3 s | 4625.7 s | 4623.6 s ± 2.5 s | 4620.9 s – 4625.7 s | 0.1% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
