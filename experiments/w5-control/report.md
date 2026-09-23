# w5-control · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 6c0881eb
配置：timing=compressed · concurrency=1 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260922T092521 | 20260922T104257 | 20260922T120038 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9633 | 0.9633 | 0.9633 | 0.9633 ± 0.0000 | 0.9633 – 0.9633 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9633 | 0.9633 | 0.9633 | 0.9633 ± 0.0000 | 0.9633 – 0.9633 | 0.0% |
| TTFT P50 | 242 ms | 243 ms | 240 ms | 242 ms ± 1 ms | 240 ms – 243 ms | 0.5% |
| TTFT P95 | 512 ms | 516 ms | 520 ms | 516 ms ± 4 ms | 512 ms – 520 ms | 0.7% |
| TTFT P99 | 869 ms | 869 ms | 876 ms | 871 ms ± 4 ms | 869 ms – 876 ms | 0.5% |
| latency P50 | 2358 ms | 2386 ms | 2373 ms | 2372 ms ± 14 ms | 2358 ms – 2386 ms | 0.6% |
| latency P95 | 22963 ms | 22965 ms | 22998 ms | 22975 ms ± 20 ms | 22963 ms – 22998 ms | 0.1% |
| latency P99 | 40106 ms | 40136 ms | 40131 ms | 40124 ms ± 16 ms | 40106 ms – 40136 ms | 0.0% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| evicted tokens | — | 958882 | 958882 | 958882 ± 0 | 958882 – 958882 | 0.0% |
| retracted requests | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 4653.0 s | 4658.5 s | 4660.1 s | 4657.2 s ± 3.7 s | 4653.0 s – 4660.1 s | 0.1% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
