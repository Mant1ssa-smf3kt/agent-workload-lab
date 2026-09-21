# baseline-c1 vs baseline-c3

配置差异（含 server 启动参数 `serve.*`）：
- `replay.concurrency`: 1 → 3

| 指标 | baseline-c1 (n=3) | baseline-c3 (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.9691 ± 0.0005 | 0.9697 ± 0.0000 | -0.0006 (-0.1%) | 1.3× |
| cache hit rate (excl. synthetic) | 0.9720 ± 0.0005 | 0.9726 ± 0.0000 | -0.0006 (-0.1%) | 1.3× |
| TTFT P50 | 247 ms ± 2 ms | 268 ms ± 1 ms | -20 ms (-7.6%) | 8.9× |
| TTFT P95 | 549 ms ± 17 ms | 563 ms ± 19 ms | -14 ms (-2.5%) | 0.7× |
| TTFT P99 | 1686 ms ± 82 ms | 1587 ms ± 11 ms | 99 ms (+6.2%) | 1.2× |
| latency P50 | 2241 ms ± 14 ms | 2336 ms ± 5 ms | -95 ms (-4.1%) | 6.9× |
| latency P95 | 22913 ms ± 266 ms | 23263 ms ± 8 ms | -350 ms (-1.5%) | 1.3× |
| latency P99 | 36422 ms ± 470 ms | 41031 ms ± 54 ms | -4609 ms (-11.2%) | 9.8× |
| prompt tokens total | 4991988 ± 0 | 4989248 ± 0 | 2740 (+0.1%) | ∞（零噪声） |
| requests | 171 ± 0 | 171 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| timeouts (censored) | — | — | — | — |
| wall | 1260.1 s ± 10.4 s | 845.0 s ± 0.2 s | 415.0 s (+49.1%) | 40.0× |

Δ = baseline-c1 − baseline-c3（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可下结论。
