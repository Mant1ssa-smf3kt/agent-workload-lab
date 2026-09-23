# w5-c4-truncate vs w5-c4

配置差异（含 server 启动参数 `serve.*`）：
- `transform`: {"name": "truncate_tool_results", "params": {"keep_recent": 4, "max_chars": 800}} → {"name": "identity", "params": {}}

| 指标 | w5-c4-truncate (n=3) | w5-c4 (n=3) | Δ (A − B) | Δ / 噪声 |
|---|---|---|---|---|
| cache hit rate | 0.8801 ± 0.0015 | 0.7467 ± 0.0217 | 0.1334 (+17.9%) | 6.1× |
| cache hit rate (excl. synthetic) | 0.8800 ± 0.0015 | 0.7464 ± 0.0218 | 0.1336 (+17.9%) | 6.1× |
| TTFT P50 | 298 ms ± 2 ms | 442 ms ± 16 ms | -144 ms (-32.6%) | 8.8× |
| TTFT P95 | 2613 ms ± 31 ms | 14259 ms ± 1480 ms | -11646 ms (-81.7%) | 7.9× |
| TTFT P99 | 7582 ms ± 91 ms | 34402 ms ± 4143 ms | -26820 ms (-78.0%) | 6.5× |
| latency P50 | 3003 ms ± 37 ms | 6108 ms ± 194 ms | -3105 ms (-50.8%) | 16.0× |
| latency P95 | 27010 ms ± 256 ms | 38326 ms ± 836 ms | -11316 ms (-29.5%) | 13.5× |
| latency P99 | 48520 ms ± 58 ms | 65084 ms ± 383 ms | -16564 ms (-25.5%) | 43.2× |
| prompt tokens total | 13776632 ± 0 | 19472018 ± 0 | -5695386 (-29.2%) | ∞（零噪声） |
| requests | 837 ± 0 | 837 ± 0 | 0 (+0.0%) | — |
| errors | 0 ± 0 | 0 ± 0 | 0 | — |
| timeouts (censored) | 0 ± 0 | 0 ± 0 | 0 | — |
| evicted tokens | 1895438 ± 20809 | 5178087 ± 420076 | -3282648 (-63.4%) | 7.8× |
| retracted requests | 0 ± 1 | 0 ± 0 | 0 | 0.6× |
| wall | 1934.1 s ± 2.5 s | 2824.8 s ± 22.6 s | -890.7 s (-31.5%) | 39.4× |

Δ = w5-c4-truncate − w5-c4（实验组 − 对照组），百分比相对对照组。Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。
**判定**：可对照；但以下指标 Δ / 噪声 < 2×，与噪声同量级，只能记为「在噪声范围内无差异」，不得据此下结论：retracted requests。
