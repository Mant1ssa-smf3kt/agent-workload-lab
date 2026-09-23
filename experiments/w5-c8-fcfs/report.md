# w5-c8-fcfs · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 8bc97bcf
配置：timing=real · concurrency=8 · transform=identity · traces=25 · timeout_s=600

| 指标 | 20260923T113442 | 20260923T123831 | 20260923T134219 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.1976 | 0.1999 | 0.1999 | 0.1991 ± 0.0013 | 0.1976 – 0.1999 | 0.7% |
| cache hit rate (excl. synthetic) | 0.1975 | 0.1998 | 0.1998 | 0.1991 ± 0.0013 | 0.1975 – 0.1998 | 0.7% |
| TTFT P50 | 17726 ms | 18173 ms | 18182 ms | 18027 ms ± 261 ms | 17726 ms – 18182 ms | 1.4% |
| TTFT P95 | 50097 ms | 52090 ms | 52096 ms | 51428 ms ± 1152 ms | 50097 ms – 52096 ms | 2.2% |
| TTFT P99 | 63495 ms | 67868 ms | 67888 ms | 66417 ms ± 2530 ms | 63495 ms – 67888 ms | 3.8% |
| latency P50 | 25327 ms | 25725 ms | 25732 ms | 25595 ms ± 232 ms | 25327 ms – 25732 ms | 0.9% |
| latency P95 | 71379 ms | 70102 ms | 70113 ms | 70531 ms ± 734 ms | 70102 ms – 71379 ms | 1.0% |
| latency P99 | 106204 ms | 106934 ms | 106952 ms | 106697 ms ± 427 ms | 106204 ms – 106952 ms | 0.4% |
| prompt tokens total | 19472018 | 19472018 | 19472018 | 19472018 ± 0 | 19472018 – 19472018 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| evicted tokens | — | 15895056 | 15895055 | 15895056 ± 1 | 15895055 – 15895056 | 0.0% |
| retracted requests | 2 | 2 | 2 | 2 ± 0 | 2 – 2 | 0.0% |
| wall | 3826.7 s | 3825.2 s | 3826.2 s | 3826.0 s ± 0.8 s | 3825.2 s – 3826.7 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
