# w3-timestamp vs w3-control

配置差异：
- `transform`: {"name": "system_timestamp", "params": {}} → {"name": "identity", "params": {}}

| 指标 | w3-timestamp (n=3) | w3-control (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.1059 ± 0.0000 | 0.9633 ± 0.0000 | -0.8574 (-89.0%) | ∞（零噪声） |
| cache hit rate (excl. synthetic) | 0.1056 ± 0.0000 | 0.9633 ± 0.0000 | -0.8576 (-89.0%) | ∞（零噪声） |
| TTFT P50 | 2306 ms ± 2 ms | 236 ms ± 1 ms | 2070 ms (+877.8%) | 838.4× |
| TTFT P95 | 5971 ms ± 4 ms | 507 ms ± 5 ms | 5465 ms (+1078.7%) | 1189.3× |
| TTFT P99 | 7668 ms ± 6 ms | 852 ms ± 0 ms | 6816 ms (+800.4%) | 1066.2× |
| latency P50 | 5550 ms ± 2 ms | 2352 ms ± 5 ms | 3197 ms (+135.9%) | 695.4× |
| latency P95 | 24577 ms ± 6 ms | 22813 ms ± 24 ms | 1764 ms (+7.7%) | 73.4× |
| latency P99 | 41619 ms ± 22 ms | 39842 ms ± 11 ms | 1777 ms (+4.5%) | 80.5× |
| prompt tokens total | 19492943 ± 0 | 19472018 ± 0 | 20925 (+0.1%) | ∞（零噪声） |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| wall | 6615.0 s ± 0.8 s | 4623.6 s ± 2.5 s | 1991.3 s (+43.1%) | 796.3× |

Δ = w3-timestamp − w3-control（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可下结论。
