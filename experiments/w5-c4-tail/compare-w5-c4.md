# w5-c4-tail vs w5-c4

配置差异（含 server 启动参数 `serve.*`）：
- `transform`: {"name": "system_timestamp", "params": {"position": "tail"}} → {"name": "identity", "params": {}}

| 指标 | w5-c4-tail (n=3) | w5-c4 (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.7688 ± 0.0056 | 0.7467 ± 0.0217 | 0.0221 (+3.0%) | 1.0× |
| cache hit rate (excl. synthetic) | 0.7685 ± 0.0056 | 0.7464 ± 0.0218 | 0.0221 (+3.0%) | 1.0× |
| TTFT P50 | 406 ms ± 4 ms | 442 ms ± 16 ms | -36 ms (-8.1%) | 2.2× |
| TTFT P95 | 13714 ms ± 379 ms | 14259 ms ± 1480 ms | -546 ms (-3.8%) | 0.4× |
| TTFT P99 | 29824 ms ± 1281 ms | 34402 ms ± 4143 ms | -4577 ms (-13.3%) | 1.1× |
| latency P50 | 5807 ms ± 40 ms | 6108 ms ± 194 ms | -301 ms (-4.9%) | 1.5× |
| latency P95 | 37124 ms ± 298 ms | 38326 ms ± 836 ms | -1202 ms (-3.1%) | 1.4× |
| latency P99 | 65174 ms ± 331 ms | 65084 ms ± 383 ms | 90 ms (+0.1%) | 0.2× |
| prompt tokens total | 19496291 ± 0 | 19472018 ± 0 | 24273 (+0.1%) | ∞（零噪声） |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| timeouts (censored) | 0 ± 0 | 0 ± 0 | 0 | — |
| evicted tokens | 4751212 ± 112487 | 5178087 ± 420076 | -426875 (-8.2%) | 1.0× |
| retracted requests | 1 ± 1 | 0 ± 0 | 1 | 0.6× |
| wall | 2741.5 s ± 12.6 s | 2824.8 s ± 22.6 s | -83.3 s (-2.9%) | 3.7× |

Δ = w5-c4-tail − w5-c4（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可对照；但以下指标 Δ / 噪声 < 2×，与噪声同量级，只能记为「在噪声范围内无差异」，不得据此下结论：cache hit rate、cache hit rate (excl. synthetic)、TTFT P95、TTFT P99、latency P50、latency P95、latency P99、evicted tokens、retracted requests。
