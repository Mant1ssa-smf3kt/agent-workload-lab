# w5-c4-truncate · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 6c0881eb
配置：timing=real · concurrency=4 · transform=truncate_tool_results · traces=25 · timeout_s=600

| 指标 | 20260922T215107 | 20260922T222322 | 20260922T225539 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.8816 | 0.8801 | 0.8786 | 0.8801 ± 0.0015 | 0.8786 – 0.8816 | 0.2% |
| cache hit rate (excl. synthetic) | 0.8815 | 0.8800 | 0.8785 | 0.8800 ± 0.0015 | 0.8785 – 0.8815 | 0.2% |
| TTFT P50 | 296 ms | 297 ms | 300 ms | 298 ms ± 2 ms | 296 ms – 300 ms | 0.7% |
| TTFT P95 | 2632 ms | 2630 ms | 2576 ms | 2613 ms ± 31 ms | 2576 ms – 2632 ms | 1.2% |
| TTFT P99 | 7600 ms | 7662 ms | 7482 ms | 7582 ms ± 91 ms | 7482 ms – 7662 ms | 1.2% |
| latency P50 | 2981 ms | 2981 ms | 3046 ms | 3003 ms ± 37 ms | 2981 ms – 3046 ms | 1.2% |
| latency P95 | 27168 ms | 27148 ms | 26715 ms | 27010 ms ± 256 ms | 26715 ms – 27168 ms | 0.9% |
| latency P99 | 48463 ms | 48516 ms | 48579 ms | 48520 ms ± 58 ms | 48463 ms – 48579 ms | 0.1% |
| prompt tokens total | 13776632 | 13776632 | 13776632 | 13776632 ± 0 | 13776632 – 13776632 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| evicted tokens | 1874576 | 1895546 | 1916193 | 1895438 ± 20809 | 1874576 – 1916193 | 1.1% |
| retracted requests | 0 | 0 | 1 | 0 ± 1 | 0 – 1 | 173.2% |
| wall | 1931.6 s | 1934.2 s | 1936.5 s | 1934.1 s ± 2.5 s | 1931.6 s – 1936.5 s | 0.1% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
