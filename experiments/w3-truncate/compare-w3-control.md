# w3-truncate vs w3-control

配置差异（含 server 启动参数 `serve.*`）：
- `transform`: {"name": "truncate_tool_results", "params": {"keep_recent": 4, "max_chars": 800}} → {"name": "identity", "params": {}}

| 指标 | w3-truncate (n=3) | w3-control (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.9102 ± 0.0000 | 0.9633 ± 0.0000 | -0.0531 (-5.5%) | ∞（零噪声） |
| cache hit rate (excl. synthetic) | 0.9101 ± 0.0000 | 0.9633 ± 0.0000 | -0.0531 (-5.5%) | ∞（零噪声） |
| TTFT P50 | 240 ms ± 1 ms | 236 ms ± 1 ms | 4 ms (+1.7%) | 5.2× |
| TTFT P95 | 695 ms ± 5 ms | 507 ms ± 5 ms | 189 ms (+37.3%) | 34.9× |
| TTFT P99 | 1006 ms ± 3 ms | 852 ms ± 0 ms | 154 ms (+18.1%) | 49.1× |
| latency P50 | 2267 ms ± 2 ms | 2352 ms ± 5 ms | -86 ms (-3.6%) | 18.7× |
| latency P95 | 21194 ms ± 13 ms | 22813 ms ± 24 ms | -1618 ms (-7.1%) | 67.4× |
| latency P99 | 39231 ms ± 5 ms | 39842 ms ± 11 ms | -611 ms (-1.5%) | 55.8× |
| prompt tokens total | 13776632 ± 0 | 19472018 ± 0 | -5695386 (-29.2%) | ∞（零噪声） |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| timeouts (censored) | — | — | — | — |
| wall | 4412.6 s ± 0.2 s | 4623.6 s ± 2.5 s | -211.0 s (-4.6%) | 84.4× |

Δ = w3-truncate − w3-control（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可下结论。
