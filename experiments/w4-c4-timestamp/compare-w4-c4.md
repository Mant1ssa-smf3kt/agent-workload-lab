# w4-c4-timestamp vs w4-c4

配置差异（含 server 启动参数 `serve.*`）：
- `transform`: {"name": "system_timestamp", "params": {}} → {"name": "identity", "params": {}}

| 指标 | w4-c4-timestamp (n=3) | w4-c4 (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.0981 ± 0.0002 | 0.7520 ± 0.0054 | -0.6539 (-87.0%) | 121.7× |
| cache hit rate (excl. synthetic) | 0.0978 ± 0.0002 | 0.7517 ± 0.0054 | -0.6539 (-87.0%) | 121.5× |
| TTFT P50 | 4907 ms ± 70 ms | 428 ms ± 8 ms | 4479 ms (+1045.6%) | 63.9× |
| TTFT P95 | 18061 ms ± 220 ms | 13107 ms ± 411 ms | 4954 ms (+37.8%) | 12.1× |
| TTFT P99 | 45842 ms ± 2214 ms | 27845 ms ± 512 ms | 17998 ms (+64.6%) | 8.1× |
| latency P50 | 10891 ms ± 160 ms | 6100 ms ± 142 ms | 4791 ms (+78.5%) | 29.9× |
| latency P95 | 50959 ms ± 644 ms | 37269 ms ± 60 ms | 13690 ms (+36.7%) | 21.2× |
| latency P99 | 92756 ms ± 55 ms | 64770 ms ± 20 ms | 27986 ms (+43.2%) | 505.6× |
| prompt tokens total | 19492943 ± 0 | 19472018 ± 0 | 20925 (+0.1%) | ∞（零噪声） |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| timeouts (censored) | 0 ± 0 | 0 ± 0 | 0 | — |
| wall | 4166.9 s ± 5.3 s | 2791.7 s ± 6.0 s | 1375.2 s (+49.3%) | 229.5× |

Δ = w4-c4-timestamp − w4-c4（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可下结论。
