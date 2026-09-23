# w5-c8-lpm · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 8bc97bcf
配置：timing=real · concurrency=8 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260923T084922 | 20260923T094533 | 20260923T103824 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.5025 | 0.5465 | 0.5389 | 0.5293 ± 0.0235 | 0.5025 – 0.5465 | 4.4% |
| cache hit rate (excl. synthetic) | 0.5019 | 0.5459 | 0.5383 | 0.5287 ± 0.0235 | 0.5019 – 0.5459 | 4.5% |
| TTFT P50 | 4919 ms | 4367 ms | 4759 ms | 4682 ms ± 284 ms | 4367 ms – 4919 ms | 6.1% |
| TTFT P95 | 41441 ms | 34421 ms | 34601 ms | 36821 ms ± 4002 ms | 34421 ms – 41441 ms | 10.9% |
| TTFT P99 | 210102 ms | 262420 ms | 275809 ms | 249443 ms ± 34722 ms | 210102 ms – 275809 ms | 13.9% |
| latency P50 | 11383 ms | 10076 ms | 10314 ms | 10591 ms ± 696 ms | 10076 ms – 11383 ms | 6.6% |
| latency P95 | 67686 ms | 69758 ms | 67147 ms | 68197 ms ± 1378 ms | 67147 ms – 69758 ms | 2.0% |
| latency P99 | 210824 ms | 264776 ms | 277292 ms | 250964 ms ± 35321 ms | 210824 ms – 277292 ms | 14.1% |
| prompt tokens total | 19403430 | 19358869 | 19405846 | 19389382 ± 26452 | 19358869 – 19405846 | 0.1% |
| requests | 835 | 832 | 835 | 834 ± 2 | 832 – 835 | 0.2% |
| errors | 2 | 5 | 2 | 3 ± 2 | 2 – 5 | 57.7% |
| timeouts (censored) | 2 | 5 | 2 | 3 ± 2 | 2 – 5 | 57.7% |
| evicted tokens | — | 9021656 | 9195550 | 9108603 ± 122962 | 9021656 – 9195550 | 1.3% |
| retracted requests | 1 | 0 | 0 | 0 ± 1 | 0 – 1 | 173.2% |
| wall | 3368.6 s | 3168.9 s | 3298.1 s | 3278.5 s ± 101.3 s | 3168.9 s – 3368.6 s | 3.1% |

**判定**：3 次以上同配置重跑，指纹一致，9 个请求超时，已按右删失计入 TTFT/latency 分位（标 ≥ 的为下界）。 可用于对照。
