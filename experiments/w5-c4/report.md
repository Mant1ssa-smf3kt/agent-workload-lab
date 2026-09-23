# w5-c4 · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 6c0881eb
配置：timing=real · concurrency=4 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260922T171229 | 20260922T175956 | 20260922T184709 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.7336 | 0.7348 | 0.7718 | 0.7467 ± 0.0217 | 0.7336 – 0.7718 | 2.9% |
| cache hit rate (excl. synthetic) | 0.7333 | 0.7344 | 0.7715 | 0.7464 ± 0.0218 | 0.7333 – 0.7715 | 2.9% |
| TTFT P50 | 426 ms | 440 ms | 459 ms | 442 ms ± 16 ms | 426 ms – 459 ms | 3.7% |
| TTFT P95 | 15211 ms | 15012 ms | 12554 ms | 14259 ms ± 1480 ms | 12554 ms – 15211 ms | 10.4% |
| TTFT P99 | 34373 ms | 30273 ms | 38559 ms | 34402 ms ± 4143 ms | 30273 ms – 38559 ms | 12.0% |
| latency P50 | 6286 ms | 6137 ms | 5900 ms | 6108 ms ± 194 ms | 5900 ms – 6286 ms | 3.2% |
| latency P95 | 38912 ms | 37368 ms | 38698 ms | 38326 ms ± 836 ms | 37368 ms – 38912 ms | 2.2% |
| latency P99 | 65087 ms | 65465 ms | 64699 ms | 65084 ms ± 383 ms | 64699 ms – 65465 ms | 0.6% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| evicted tokens | 5431692 | 5409372 | 4693196 | 5178087 ± 420076 | 4693196 – 5431692 | 8.1% |
| retracted requests | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 2844.4 s | 2830.1 s | 2800.1 s | 2824.8 s ± 22.6 s | 2800.1 s – 2844.4 s | 0.8% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
