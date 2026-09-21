# w4-c4 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer d77ffcc4
配置：timing=real · concurrency=4 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260920T150551 | 20260920T155232 | 20260920T163903 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.7458 | 0.7553 | 0.7550 | 0.7520 ± 0.0054 | 0.7458 – 0.7553 | 0.7% |
| cache hit rate (excl. synthetic) | 0.7455 | 0.7550 | 0.7547 | 0.7517 ± 0.0054 | 0.7455 – 0.7550 | 0.7% |
| TTFT P50 | 420 ms | 435 ms | 430 ms | 428 ms ± 8 ms | 420 ms – 435 ms | 1.9% |
| TTFT P95 | 13580 ms | 12835 ms | 12907 ms | 13107 ms ± 411 ms | 12835 ms – 13580 ms | 3.1% |
| TTFT P99 | 28435 ms | 27550 ms | 27548 ms | 27845 ms ± 512 ms | 27548 ms – 28435 ms | 1.8% |
| latency P50 | 6265 ms | 6019 ms | 6017 ms | 6100 ms ± 142 ms | 6017 ms – 6265 ms | 2.3% |
| latency P95 | 37231 ms | 37237 ms | 37339 ms | 37269 ms ± 60 ms | 37231 ms – 37339 ms | 0.2% |
| latency P99 | 64784 ms | 64746 ms | 64779 ms | 64770 ms ± 20 ms | 64746 ms – 64784 ms | 0.0% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 2798.6 s | 2787.8 s | 2788.7 s | 2791.7 s ± 6.0 s | 2787.8 s – 2798.6 s | 0.2% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
