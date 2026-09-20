# w3-timestamp · 方差

环境：GPU NVIDIA GeForce RTX 4090 · sglang 0.5.20 · model Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer 2ce925b8
配置：timing=compressed · concurrency=1 · transform=system_timestamp · traces=25

| 指标 | 20260919T151600 | 20260919T170618 | 20260919T185637 | mean ± std | min – max | CV |
|---|---|---|---|---|---|---|
| cache hit rate | 0.1059 | 0.1059 | 0.1059 | 0.1059 ± 0.0000 | 0.1059 – 0.1059 | 0.0% |
| cache hit rate (excl. synthetic) | 0.1056 | 0.1056 | 0.1056 | 0.1056 ± 0.0000 | 0.1056 – 0.1056 | 0.0% |
| TTFT P50 | 2305 ms | 2308 ms | 2303 ms | 2306 ms ± 2 ms | 2303 ms – 2308 ms | 0.1% |
| TTFT P95 | 5966 ms | 5974 ms | 5973 ms | 5971 ms ± 4 ms | 5966 ms – 5974 ms | 0.1% |
| TTFT P99 | 7670 ms | 7673 ms | 7661 ms | 7668 ms ± 6 ms | 7661 ms – 7673 ms | 0.1% |
| latency P50 | 5548 ms | 5549 ms | 5552 ms | 5550 ms ± 2 ms | 5548 ms – 5552 ms | 0.0% |
| latency P95 | 24574 ms | 24572 ms | 24583 ms | 24577 ms ± 6 ms | 24572 ms – 24583 ms | 0.0% |
| latency P99 | 41632 ms | 41593 ms | 41631 ms | 41619 ms ± 22 ms | 41593 ms – 41632 ms | 0.1% |
| prompt tokens total | 19492943 | 19492943 | 19492943 | 19492943 ± 0 | 19492943 – 19492943 | 0.0% |
| requests | 837 | 837 | 837 | 837 ± 0 | 837 – 837 | 0.0% |
| errors | 0 | 0 | 0 | 0 ± 0 | 0 – 0 | — |
| wall | 6614.5 s | 6615.9 s | 6614.6 s | 6615.0 s ± 0.8 s | 6614.5 s – 6615.9 s | 0.0% |

**判定**：3 次以上同配置重跑，指纹一致，无错误；可用于对照。
