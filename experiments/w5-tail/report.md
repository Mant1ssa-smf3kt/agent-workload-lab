# w5-tail · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 6c0881eb
配置：timing=compressed · concurrency=1 · transform=system_timestamp · traces=25 · timeout_s=600

| 指标 | 20260922T131821 | 20260922T143608 | 20260922T155359 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.9620 | 0.9620 | 0.9620 | 0.9620 ± 0.0000 | 0.9620 – 0.9620 | 0.0% |
| cache hit rate (excl. synthetic) | 0.9620 | 0.9620 | 0.9620 | 0.9620 ± 0.0000 | 0.9620 – 0.9620 | 0.0% |
| TTFT P50 | 250 ms | 254 ms | 249 ms | 251 ms ± 3 ms | 249 ms – 254 ms | 1.2% |
| TTFT P95 | 523 ms | 520 ms | 523 ms | 522 ms ± 1 ms | 520 ms – 523 ms | 0.3% |
| TTFT P99 | 849 ms | 871 ms | 865 ms | 862 ms ± 11 ms | 849 ms – 871 ms | 1.3% |
| latency P50 | 2364 ms | 2375 ms | 2371 ms | 2370 ms ± 6 ms | 2364 ms – 2375 ms | 0.2% |
| latency P95 | 22988 ms | 23034 ms | 22984 ms | 23002 ms ± 28 ms | 22984 ms – 23034 ms | 0.1% |
| latency P99 | 40141 ms | 40205 ms | 40159 ms | 40168 ms ± 33 ms | 40141 ms – 40205 ms | 0.1% |
| prompt tokens total | 19496291 | 19496291 | 19496291 | 19496291 ± 0 | 19496291 – 19496291 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| evicted tokens | 984958 | 984833 | 984833 | 984875 ± 72 | 984833 – 984958 | 0.0% |
| retracted requests | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 4663.9 s | 4667.7 s | 4666.0 s | 4665.9 s ± 1.9 s | 4663.9 s – 4667.7 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
