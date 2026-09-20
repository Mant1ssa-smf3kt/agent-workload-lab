# w3-tools-rotate vs w3-control

配置差异：
- `transform`: {"name": "tools_rotate", "params": {}} → {"name": "identity", "params": {}}

| 指标 | w3-tools-rotate (n=3) | w3-control (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.3150 ± 0.0000 | 0.9633 ± 0.0000 | -0.6483 (-67.3%) | ∞（零噪声） |
| cache hit rate (excl. synthetic) | 0.3150 ± 0.0000 | 0.9633 ± 0.0000 | -0.6483 (-67.3%) | ∞（零噪声） |
| TTFT P50 | 1231 ms ± 2 ms | 236 ms ± 1 ms | 995 ms (+421.9%) | 454.8× |
| TTFT P95 | 5951 ms ± 3 ms | 507 ms ± 5 ms | 5444 ms (+1074.7%) | 1185.0× |
| TTFT P99 | 7684 ms ± 54 ms | 852 ms ± 0 ms | 6832 ms (+802.2%) | 126.8× |
| latency P50 | 5237 ms ± 14 ms | 2352 ms ± 5 ms | 2884 ms (+122.6%) | 213.0× |
| latency P95 | 24076 ms ± 6 ms | 22813 ms ± 24 ms | 1263 ms (+5.5%) | 52.6× |
| latency P99 | 41128 ms ± 20 ms | 39842 ms ± 11 ms | 1286 ms (+3.2%) | 64.5× |
| prompt tokens total | 19472018 ± 0 | 19472018 ± 0 | 0 (+0.0%) | — |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| wall | 6243.7 s ± 2.6 s | 4623.6 s ± 2.5 s | 1620.1 s (+35.0%) | 621.2× |

Δ = w3-tools-rotate − w3-control（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可下结论。
