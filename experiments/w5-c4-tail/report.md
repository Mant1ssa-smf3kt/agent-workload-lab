# w5-c4-tail · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 6c0881eb
配置：timing=real · concurrency=4 · transform=system_timestamp · traces=25 · timeout_s=600

| 指标 | 20260922T193353 | 20260922T201929 | 20260922T210508 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.7736 | 0.7700 | 0.7627 | 0.7688 ± 0.0056 | 0.7627 – 0.7736 | 0.7% |
| cache hit rate (excl. synthetic) | 0.7734 | 0.7698 | 0.7624 | 0.7685 ± 0.0056 | 0.7624 – 0.7734 | 0.7% |
| TTFT P50 | 401 ms | 409 ms | 408 ms | 406 ms ± 4 ms | 401 ms – 409 ms | 1.0% |
| TTFT P95 | 13412 ms | 13589 ms | 14140 ms | 13714 ms ± 379 ms | 13412 ms – 14140 ms | 2.8% |
| TTFT P99 | 31001 ms | 30012 ms | 28460 ms | 29824 ms ± 1281 ms | 28460 ms – 31001 ms | 4.3% |
| latency P50 | 5761 ms | 5821 ms | 5837 ms | 5807 ms ± 40 ms | 5761 ms – 5837 ms | 0.7% |
| latency P95 | 36984 ms | 37466 ms | 36921 ms | 37124 ms ± 298 ms | 36921 ms – 37466 ms | 0.8% |
| latency P99 | 64794 ms | 65400 ms | 65328 ms | 65174 ms ± 331 ms | 64794 ms – 65400 ms | 0.5% |
| prompt tokens total | 19496291 | 19496291 | 19496291 | 19496291 ± 0 | 19496291 – 19496291 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| timeouts (censored) | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| evicted tokens | 4652480 | 4727486 | 4873669 | 4751212 ± 112487 | 4652480 – 4873669 | 2.4% |
| retracted requests | 0 | 0 | 2 | 1 ± 1 | 0 – 2 | 173.2% |
| wall | 2733.3 s | 2735.3 s | 2756.0 s | 2741.5 s ± 12.6 s | 2733.3 s – 2756.0 s | 0.5% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
