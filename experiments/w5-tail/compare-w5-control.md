# w5-tail vs w5-control

配置差异（含 server 启动参数 `serve.*`）：
- `transform`: {"name": "system_timestamp", "params": {"position": "tail"}} → {"name": "identity", "params": {}}

| 指标 | w5-tail (n=3) | w5-control (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.9620 ± 0.0000 | 0.9633 ± 0.0000 | -0.0013 (-0.1%) | ∞（零噪声） |
| cache hit rate (excl. synthetic) | 0.9620 ± 0.0000 | 0.9633 ± 0.0000 | -0.0013 (-0.1%) | ∞（零噪声） |
| TTFT P50 | 251 ms ± 3 ms | 242 ms ± 1 ms | 9 ms (+3.8%) | 3.1× |
| TTFT P95 | 522 ms ± 1 ms | 516 ms ± 4 ms | 6 ms (+1.2%) | 1.6× |
| TTFT P99 | 862 ms ± 11 ms | 871 ms ± 4 ms | -10 ms (-1.1%) | 0.8× |
| latency P50 | 2370 ms ± 6 ms | 2372 ms ± 14 ms | -2 ms (-0.1%) | 0.2× |
| latency P95 | 23002 ms ± 28 ms | 22975 ms ± 20 ms | 27 ms (+0.1%) | 1.0× |
| latency P99 | 40168 ms ± 33 ms | 40124 ms ± 16 ms | 44 ms (+0.1%) | 1.4× |
| prompt tokens total | 19496291 ± 0 | 19472018 ± 0 | 24273 (+0.1%) | ∞（零噪声） |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| timeouts (censored) | 0 ± 0 | 0 ± 0 | 0 | — |
| evicted tokens | 984875 ± 72 | 958882 ± 0 | 25993 (+2.7%) | 360.2× |
| retracted requests | 0 ± 0 | 0 ± 0 | 0 | — |
| wall | 4665.9 s ± 1.9 s | 4657.2 s ± 3.7 s | 8.7 s (+0.2%) | 2.3× |

Δ = w5-tail − w5-control（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可对照；但以下指标 Δ / 噪声 < 2×，与噪声同量级，只能记为「在噪声范围内无差异」，不得据此下结论：TTFT P95、TTFT P99、latency P50、latency P95、latency P99。
