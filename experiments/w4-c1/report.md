# w4-c1 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer d77ffcc4
配置：timing=real · concurrency=1 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260920T100749 | 20260920T114711 | 20260920T132634 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9633 | 0.9633 | 0.9633 | 0.9633 ± 0.0000 | 0.9633 – 0.9633 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9633 | 0.9633 | 0.9633 | 0.9633 ± 0.0000 | 0.9633 – 0.9633 | 0.0% |
| TTFT P50 | 238 ms | 242 ms | 240 ms | 240 ms ± 2 ms | 238 ms – 242 ms | 0.6% |
| TTFT P95 | 504 ms | 510 ms | 505 ms | 506 ms ± 3 ms | 504 ms – 510 ms | 0.6% |
| TTFT P99 | 859 ms | 855 ms | 854 ms | 856 ms ± 3 ms | 854 ms – 859 ms | 0.3% |
| latency P50 | 2342 ms | 2358 ms | 2351 ms | 2350 ms ± 8 ms | 2342 ms – 2358 ms | 0.3% |
| latency P95 | 22703 ms | 22704 ms | 22724 ms | 22710 ms ± 12 ms | 22703 ms – 22724 ms | 0.1% |
| latency P99 | 39774 ms | 39852 ms | 39667 ms | 39765 ms ± 93 ms | 39667 ms – 39852 ms | 0.2% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 5959.7 s | 5959.7 s | 5954.6 s | 5958.0 s ± 2.9 s | 5954.6 s – 5959.7 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
