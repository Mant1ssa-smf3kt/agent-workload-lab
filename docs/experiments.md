# 实验日志

每次实验一条，含负面结果（CLAUDE.md §9）。格式：

```
## <日期> · <experiments/目录名>
- 变量：只动了什么
- 环境：指纹文件路径（GPU / SGLang / 模型 / pi / replayer commit）
- 结果：数字来源于哪个 artifact（P50/P95/P99，三次重跑的方差）
- 结论：一句话；噪声 ≥ 效应时写「作废」
```

（尚无实验。W1 只有录制侧画像，不含重放数字。）

## 2026-09-18 · experiments/profile（录制侧画像，非重放）
- 变量：无（W1 刻画）
- 环境：录制侧 zai/glm-5.2:off，pi 0.85.1，extension 0.1.0，contextWindow 覆盖 65536；无 GPU
- 输入：3 条 trace（minimind 7 req / Learn-OpenClaw 41 req / reactive-resume 124 req，1 次 compaction）；1 条空会话按 `--min-requests 1` 跳过。sha256 见 `experiments/profile/meta.json`
- 结果：`experiments/profile/profile.md`。跨轮共享前缀比例 P50 0.988（append-only 基线）；reactive-resume 在 req 84→85 compaction 处共享前缀 0.990→0.136、相同前导消息 202→1、云端 cacheRead/prompt 0.99→0.148（`out/requests.csv`）
- 结论：录制链路可用；compaction 是已观察到的最大缓存失效事件。摘要调用未被记为 request（见 later.md）

## 2026-09-18 · experiments/baseline-c1（单并发、真实时序）— 2 次完成 + 1 次部分
- 变量：无（基线）。config = `experiments/baseline-c1/config.yaml`（concurrency 1, timing real, gap_scale 1, max_gap_s 30, output=recorded+ignore_eos, compaction=synthesize, warmup 2）
- 环境：RTX 4090 (24564 MiB, driver 580.105.08, CUDA 13.0) · sglang 0.5.20 · torch 2.13.0+cu130 · Qwen/Qwen3-8B-FP8 (config sha 79e454d6…) · serve args 见 `experiments/baseline-c1/serve-fingerprint.json`（YaRN×2 → 65536、prefill CUDA graph 关、cache-report 开、KV 池 78384 token）· pi 0.85.1 · extension 0.1.0
- replayer commit：指纹里为空（远端无 .git，`.sync-commit` 机制在本批之后才加，`c3addcc`）。本批代码 = `faf2020`：`replay/` 自 `b2bf67d` 起无改动，`scripts/serve.sh` 为 `faf2020` 版本
- 输入：3 条 trace（同 `experiments/profile/meta.json` 的 sha256），173 步含 1 个合成 compaction；2 个 warmup 请求不计
- 结果（`experiments/baseline-c1/report.md`，来源 `out/20260918T222305`、`out/20260918T224449`）：
  - cache hit rate（§5，Σcached/Σprompt）0.9688 / 0.9696；不含合成 0.9717 / 0.9725
  - TTFT P50/P95/P99 = 250/558/1739 ms 与 246/560/1727 ms；latency P50/P95/P99 ≈ 2.25 s / 23.1 s / 36.7 s（长输出 decode 主导，~55 tok/s）
  - wall 1266 s ×2，0 错误，两次所有指标 CV ≤ 1.2%
  - compaction 边界（trace 20260918T114524 idx 84→87，两次 run 数字一致）：命中 0.991 → 合成 compaction 0.197 → **compaction 后首条 0.144，TTFT 315 ms → 3954 ms** → 0.993 恢复。见 `out/*/requests.jsonl`
- 2026-09-18 的第 3 次（`out/20260918T230558-partial`，97/173）按用户要求中止，不计入
- 2026-09-19 补跑第 3 次（`out/20260919T083248`，服务重启后冷缓存起步，指纹 `serve-20260919T083143.json`，参数与前两次相同）：hit 0.9688、TTFT P50/P95/P99 246/529/1591 ms、wall 1248 s、0 错误
- 三次汇总（`report.md`）：cache hit 0.9691 ± 0.0005（CV 0.0%）、TTFT P50 247 ± 2 ms（0.9%）、P95 549 ± 17 ms（3.1%）、P99 1686 ± 82 ms（4.9%）、latency P95 22.9 ± 0.27 s
- 结论：**方差已确认，基线成立。** 单并发下噪声 ≤ 5%（P99），后续对照效应需 ≥ 2× 于此。
- 待修：合成 compaction 请求去掉了 `tools`，而 chat template 把 tools 渲染进 system 段，导致该请求自身命中仅 0.197（预期 ~0.99）；W3 前改为保留 tools（见 later.md）

## 2026-09-19 · experiments/baseline-c3（3 条轨迹同时重放、真实时序）— 3 次完成
- 变量：与 baseline-c1 只差 `replay.concurrency: 1 → 3`（`compare-baseline-c3.md` 自动核对，仅此一项）。原名 baseline-c4 改为 c3：只有 3 条 trace，调度器取 min(concurrency, 轨迹数)，写 4 是假的。
- 环境：同 c1（RTX 4090 / sglang 0.5.20 / Qwen3-8B-FP8 / 同一启动参数，指纹 `experiments/baseline-c3/serve-fingerprint.json`，服务 2026-09-19 08:31 启动后连跑 c1#3 + c3×3 未重启）。replayer 代码同 c1 批（指纹 commit 为空，`.sync-commit` 本批仍挂起以保持一致；代码 = `faf2020` 的 replay/）
- 结果（`report.md`，3 次）：cache hit **0.9697 ± 0.0000**；TTFT P50/P95/P99 = 268 ± 1 / 563 ± 19 / 1587 ± 11 ms；latency P50/P95/P99 = 2336 ± 5 / 23263 ± 8 / **41031 ± 54** ms；wall 845.0 ± 0.2 s；0 错误。判定：可用于对照。
- 对照 c1 → c3（`experiments/baseline-c1/compare-baseline-c3.md`）：
  - cache hit +0.0006（1.3× 噪声）：**无变化**。三条轨迹除 system prompt 外无公共前缀，也没互相挤出 KV 池
  - TTFT P50 +20 ms（+8%，8.9× 噪声）：真实但小；P95/P99 在噪声内
  - latency P99 **+4.6 s（+12.7%，9.8× 噪声）**：长 decode 在 2–3 条同飞时被拖慢——多并发的可测效应是 decode 竞争，不是缓存
  - wall −33%
- 实际并发（c3 run1 `requests.jsonl` 算得）：845 s 里服务器忙 587 s，其中 3 条同飞仅 14%、2 条 33%、1 条 53%；38 个 >40k 的大 prompt 全在 310–840 s，而另两条轨迹 359 s 即结束——**重负载阶段基本是单条**。
- 结论：3 条 trace + 真实时序下 concurrency=3 压不到缓存；W4 的驱逐/饥饿实验需要更多轨迹（录第二批 20 条，`docs/recording-tasks.md`）或带盐复制重轨迹。
- 小瑕疵：c1 与 c3 的 prompt tokens total 差 2740（0.05%）——`warmup_requests: 2` 按全局发送顺序剔除，并发下剔除的是不同的两条请求。下版改为按第一条轨迹的前 N 步剔除（见 later.md）。

## 2026-09-19 · experiments/profile 更新：25 条 trajectory（W1 交付物完成）
- 输入：case1–3（手动）+ t01–t05（手动，worktree）+ t06–t22（`scripts/record_batch.py` 自动，RPC 模式）；1 条空会话按 `--min-requests 1` 跳过；t23 未录（zai 余额）。sha256 见 `experiments/profile/meta.json`。全部 glm-5.2 thinking off、contextWindow 65536、outcome 全 done、有 shutdown。
- 形状（`experiments/profile/profile.md`）：每会话请求数 P50/P95/P99 = 28/75/124；最大 prompt tokens P50 25.4k、P95 48.6k；每请求 prompt tokens P50 21.5k（n=837）；跨轮共享前缀比例 P50 0.980；工具 500 bash / 278 read / 159 edit / 30 write；output tokens P50 114、P95 1200。
- compaction：2 条（case3 @49k、t21 @48.6k）。t12/t16/t19 分别到 34.8k/44.5k/43.5k 未过 49152 阈值（每轮平均涨 0.5–1.5k token，轮数不够）。第五批 t21 用 5 个连续 prompt 推过阈值；t22 到 35k。
- 结论：W1「录制 20–30 条 + 画像表」完成。W3 在这 25 条上跑。

## 2026-09-19/20 · experiments/w3-{control,timestamp,tools-rotate,truncate}（W3 上下文改写对照）— 各 3 次完成
- 变量：与 `w3-control`（`transform: identity`）只差 `transform` 一项（三份 `compare-w3-control.md` 自动核对，仅此一项）。其余逐字节相同：25 条 trace（sorted）、concurrency 1、timing compressed、seed 0、output recorded + ignore_eos、compaction synthesize、warmup 2。
- 环境：RTX 4090 (driver 580.105.08, CUDA 13.0) · sglang 0.5.20 · torch 2.13.0+cu130 · Qwen/Qwen3-8B-FP8 (config sha 79e454d6…) · serve args 同 baseline（YaRN×2 → 65536、chunked-prefill 8192、lpm、prefill CUDA graph 关、random-seed 0）· pi 0.85.1 · extension 0.1.0 · replayer `2ce925b8`（`.sync-commit`，clean）。指纹 `experiments/w3-*/out/*/fingerprint.json`。服务 2026-09-19 11:23 启动后 12 个 run 连跑未重启（`scripts/run-batch.sh 3 …`，11:24 → 次日 05:40）。
- 输入：25 条 trace，837 请求/run（含合成 compaction 2 条），2 个 warmup 不计。四组 requests=837、errors=0。
- 结果（各 `report.md`，n=3；`compare-w3-control.md` 为对照，Δ 相对 control）：

  | 组 | cache hit | TTFT P50 / P95 / P99 (ms) | latency P50 / P95 / P99 (ms) | prompt tok 总 | wall (s) |
  |---|---|---|---|---|---|
  | control | 0.9633 ± 0.0000 | 236 / 507 / 852 | 2352 / 22813 / 39842 | 19.47M | 4623.6 ± 2.5 |
  | system_timestamp | **0.1059** ± 0.0000 | 2306 / **5971** / 7668 | 5550 / 24577 / 41619 | 19.49M (+0.1%) | 6615.0 ± 0.8 |
  | tools_rotate | **0.3150** ± 0.0000 | 1231 / 5951 / 7684 | 5237 / 24076 / 41128 | 19.47M (±0) | 6243.7 ± 2.6 |
  | truncate_tool_results | 0.9102 ± 0.0000 | 240 / 695 / 1006 | 2267 / 21194 / 39231 | 13.78M (−29.2%) | 4412.6 ± 0.2 |

  - 方差：四组 cache hit 三次逐字节相同（std 为浮点误差，表里显示 ∞）；TTFT/latency 各分位 std ≤ 54 ms，CV ≤ 1%。所有对照 Δ/噪声 ≥ 5×，最小的是 truncate 的 TTFT P50（−4 ms，5.2×）。
  - timestamp vs control：hit −0.8574（−89.0%）；TTFT P50 +877.8%、**P95 +1078.7%**（507 → 5971 ms）、P99 +800.4%；latency P50 +135.9%、**P95 +7.7%**、P99 +4.5%；wall +43.1%。
  - tools_rotate vs control：hit −0.6483（−67.3%）；TTFT P95 +1074%；latency P50 +122.7%、P95 +5.5%；wall +35.0%。
  - truncate vs control：hit −0.0531（−5.5%）；TTFT P95 +37.3%、P99 +18.1%；latency P50 −3.6%、P95 −7.1%；prompt tokens −29.2%；wall −4.6%。
- 机制（`out/*/requests.jsonl`，run 1，按请求算 `res_cached_tokens`）：control 每请求命中 P50 22167 tok（prompt P50 22759）。timestamp 每请求命中 P50 3369、**最大 3723**——只剩 system prompt 里时间戳之前的那段，tools + 全部 messages 每轮从头 prefill，98% 请求命中率 < 0.5。tools_rotate 命中 P50 3752 但最大 21848：轮转周期对齐时整段前缀能命中，所以 0.315 > 0.106；59% 请求 < 0.5。truncate 命中 P50 13942 / prompt 15139，8% 请求 < 0.5——只有截断窗口滑过的那些轮次失配。
- 结论：
  1. **头条数字成立**（口径见 `docs/decisions.md` 2026-09-20）：在 system prompt 末尾写当前时间，使 radix cache 命中率 0.9633 → 0.1059，单轮 P95 延迟 +7.7%（TTFT P95 +1078.7%，507 → 5971 ms）；append-only（control）为 0.9633。
  2. 单轮 P95 只涨 7.7% 而 TTFT P95 涨 10.8×：P95 轮次是长输出轮（输出按录制长度 decode：P50 114 / P95 1210 / max 4339 tok，`requests.jsonl` `res_completion_tokens`），decode 主导端到端；prefill 从 0.5 s 变 6 s 在 P50 上是 +136%，到 P95 被摊薄。**改头（system/tools）的代价主要落在 TTFT 与 P50，不是尾延迟**。
  3. 改头 ≫ 改尾：改 system prompt 末尾（timestamp）与改 tools 顺序（rotate）都把命中打到 ≤ 0.32；改旧工具结果（truncate）只掉 5 个点，还省 29% prompt token、P95 反降 7%。W1 本地按 chat template 预估的共享前缀（0.110 / 0.110 / 0.983）与实测（0.106 / 0.315 / 0.910）方向一致；rotate 高于预估是因为轮转周期对齐，truncate 低于预估是因为截断改变的是「后一轮 prompt 的中段」而非只在尾部追加。
  4. 单并发无内存压力下命中率三次完全一致，噪声全在延迟上（≤ 1%）；对照效应远超 §9 的 2× 门槛。
- 已知偏差：compressed 时序，不与 real 模式的 baseline-c1/c3 同表；timestamp 组 prompt tokens 多 20925（每请求 +25 tok 时间戳本身），不影响结论。

## 2026-09-20/21 · experiments/w4-c{1,2,4,8} + w4-c4-timestamp（W4 并发扫描与并发下的 timestamp 对照）— 各 3 次完成
- 变量：并发扫描四组与 `w4-c1` 只差 `replay.concurrency`（1/2/4/8）；`w4-c4-timestamp` 与 `w4-c4` 只差 `transform`（identity → system_timestamp）。五份 `compare-*.md` 自动核对均为单一差异。其余逐字节相同：25 条 trace（sorted）、**timing real**（gap_scale 1、max_gap_s 30）、seed 0、output recorded + ignore_eos、compaction synthesize、warmup 2、`server.timeout_s` 600。
- 环境：RTX 4090 · sglang 0.5.20 · Qwen/Qwen3-8B-FP8 · serve args 同 W3（YaRN×2 → 65536、chunked-prefill 8192、**schedule-policy lpm**、mem-fraction 0.85、random-seed 0）· pi 0.85.1 · replayer `d77ffcc4`（`.sync-commit`，clean）。指纹 `experiments/w4-*/out/*/fingerprint.json`。服务 2026-09-20 10:06 启动后 15 个 run 连跑未重启（10:07 → 次日 02:14），顺序 c1×3 → c4×3 → c4-timestamp×3 → c8×3 → c2×3。
- 输入：25 条 trace，837 请求/run（含合成 compaction 2 条），2 个 warmup 不计。c1/c2/c4/c4-timestamp errors=0；**c8 三次共 11 个 `ReadTimeout`**（见下）。
- 口径变更（`docs/decisions.md` 2026-09-21）：超时请求按右删失计入 TTFT/latency 分位。五组 `summary.json` 已用 `just resummarize` 从 `requests.jsonl` 重算；12 个零错误 run 数字逐字节不变，只有 c8 的分位变化（旧值留在 `summary.prev.json`）。
- 结果（各 `report.md`，n=3；ms）：

  | 组 | cache hit | TTFT P50 / P95 / P99 | latency P50 / P95 / P99 | 驱逐 tok/次 | 队列非空采样占比 | wall (s) |
  |---|---|---|---|---|---|---|
  | c1 | 0.9633 ± 0.0000 | 240 / 506 / 856 | 2350 / 22710 / 39765 | 0.96M | 0% | 5958 ± 3 |
  | c2 | 0.9626 ± 0.0001 | 261 / 544 / 1643 (CV 22%) | 2548 / 23973 / 41092 | 0.97M | 1.6% | 3175 ± 1 |
  | c4 | 0.7520 ± 0.0054 | 428 / **13107** / 27845 | 6100 / 37269 / 64770 | 5.0–5.2M | 48–50% | 2792 ± 6 |
  | c8 | 0.5309 ± 0.0155 | 4674 / 37104 (CV 9%) / 223480 (CV 17%) | 10561 / 70486 / 231259 (CV 14%) | 9.0–9.6M | 79–85% | 3237 ± 70 |
  | c4-timestamp | **0.0981** ± 0.0002 | 4907 / 18061 / 45842 | 10891 / 50959 / 92756 | **17.83M** | 51–53% | 4167 ± 5 |

  驱逐量 = `metrics_after − metrics_before` 的 `sglang:evicted_tokens_total`（c1 第一次 run 无 before 快照，取后两次）；队列占比 = `metrics_samples.jsonl` 中 `sglang:num_queue_reqs > 0` 的采样比例；每 run prompt tokens 总量 19.47M（c8 因超时少 0.5%）。
- 对照（`compare-*.md`，Δ 相对对照组）：
  - c2 vs c1：hit −0.1%、TTFT P50 +8.6%、P95 +7.4%、latency P95 +5.6%、P99 +3.3%（Δ/噪声 ≥ 5.8×）；TTFT P99 +91.9% 但仅 2.2× 噪声，**不下结论**。
  - **c4 vs c1**：hit −21.9%（0.9633 → 0.7520）；TTFT P50 +78.4%、**P95 +2488.5%**（506 → 13107 ms）、P99 +3153.4%；latency P50 +159.5%、**P95 +64.1%**、P99 +62.9%。全部 ≥ 23× 噪声。
  - c8 vs c4：hit −29.4%（→ 0.5309）；TTFT P50 +991.2%、P95 +183.1%、P99 +702.6%；latency P50 +73.1%、P95 +89.1%、P99 +257.0%（5.1–16×）。
  - **c4-timestamp vs c4**：hit −87.0%（0.7520 → 0.0981）；TTFT P50 +1045.6%、P95 +37.8%、P99 +64.6%；latency P50 +78.5%、**P95 +36.7%**（37269 → 50959 ms）、P99 +43.2%；wall +49.3%。全部 ≥ 8× 噪声。
- c8 的 11 个超时（`out/*/requests.jsonl`，`res_error` = `ReadTimeout`，`res_ttfb_ms` 为空即服务端 600 s 内未发响应头）：6 个在同一条 125 请求的长轨迹（`20260918T114524`，turn 34–44，prompt 25.6–32.2k）上成对出现（超时后下一轮紧接着再超时）；另 5 个里 3 个是某个 run 的 `turn 0`，含一条冷启动请求（prompt 1675、录制 cache_read 0）。全部发生在各 run 的前 1600 s（8 条同飞阶段）。~~`sglang:num_retracted_reqs` 三次均为 0~~（2026-09-23 更正：该 gauge 每周期清零，不能用来数回撤；累计计数器 `num_retracted_requests_total` 显示三次分别回撤 1 / 2 / 0 个请求），`num_running_reqs` 最大 8、`num_queue_reqs` 最大 7。
- 结论：
  1. **多并发下的退化来自 radix 前缀驱逐 + 排队，不是回撤。** ~~五组 15 个 run `num_retracted_reqs` 全为 0——`w4-c8/config.yaml` 里「预期出现 retraction」**未发生**（负面结果）。~~（2026-09-23 更正：回撤发生过但罕见——c4 每 run 1/4/4、c4-timestamp 2/2/1、c8 1/2/0、c1/c2 为 0，被回撤输入 token 是驱逐量的 0.26–1.6%；本句的定性结论不变。见本文件 2026-09-23 条目与 `docs/decisions.md` 2026-09-23。）命中率随并发下降（0.963 → 0.963 → 0.752 → 0.531）与驱逐量同步上升（1M → 1M → 5M → 9M tok/run），KV 池 78k token 装不下 4 条以上 20–50k 的上下文。
  2. **悬崖在 c2 → c4**：c2 相对 c1 各项 ≤ 9%（队列非空 1.6%），c4 起 TTFT P95 跳 24×、队列有一半时间非空。c8 队列 80% 时间非空、最深 7，尾部出现 ≥ 600 s 的饥饿。
  3. **饥饿的形态**：超时集中在最长的那条轨迹与 run 首请求。LPM 调度按最长前缀匹配排序，前缀被驱逐的长请求与没有前缀的新请求排到最后，在 8 条同飞时可等超过 10 分钟（机制推断；数据只到调度器指标与超时分布）。
  4. **缓存失效的代价随并发放大**：timestamp 改写在 c4/real 下使单轮 P95 +36.7%（TTFT P95 +37.8%），而 W3 在 c1/compressed 下为 +7.7%（TTFT P95 +1078.7%）。两者时序模式不同不同表；但 W4-c1（real）与 W3-control（compressed）各分位差 ≤ 1.7%，支持 decisions 2026-09-19「单并发下两种时序数字一致」。单并发时失效只推高 TTFT、被 decode 摊薄；多并发时多出的 17.8M 驱逐 tok 的重 prefill 占住了 GPU，把所有人的尾延迟一起抬高。
  5. 方差：c1/c2/c4/c4-timestamp 各分位 CV ≤ 4.8%（c2 TTFT P99 22% 例外）；c8 的 TTFT/latency P99 CV 14–17%，超时数 2/4/5 次，**c8 只下方向性结论**，其绝对分位数是删失下界与高噪声的组合。
- 未做：c3（用户判断意义不大）、c8 调大 timeout 重跑（删失口径已给出下界）、hint 实验（CLAUDE.md §11 可砍项）。见 `docs/decisions.md` 2026-09-21。

## 2026-09-22 · W5 自动链路（`scripts/run-w5.sh`）— 批 1、2 完成；批 3 因启动竞态未运行
- 批 1（`w5-control`、`w5-tail`）与批 2（`w5-c4`、`w5-c4-tail`、`w5-c4-truncate`）各 3 次，15 个 run errors 全为 0（`batch-w5-{1,2}.log`）。`out/` 已于 2026-09-23 拉回本地；报告与对照待出，结论另起条目。
- **批 3（`w5-c8-lpm`、`w5-c8-fcfs`）0 个 run。** 日志留档于 `experiments/w5-c8-lpm/out/failed-20260922-race/`（不入库；远端原件改名为 `*.failed-20260922.log`）。经过（`w5-chain.log` 与两份 serve 日志）：
  1. 23:28:03 起 lpm server。`start_server` 10 s 后用 `pgrep "python -m sglang.launch_server"` 判活，但 `serve.sh` 在 `exec python` 前要先跑 `fingerprint.sh`（该次 python 首行日志在 23:28:22），于是被误判为「exited early」，其实 lpm server 仍在加载（23:28:50 ready）。
  2. 23:28:13 脚本接着起 fcfs server，撞上正在加载的 lpm 进程（占 21.42 GiB），`torch.OutOfMemoryError` 退出。
  3. fcfs 等待循环里 `pgrep` 匹配到的是存活的 lpm 进程，所以没能判出 fcfs 已退出，空等 15 min 超时；随后 `stop_server` 杀掉 lpm，链路按设计关机。
- 修复（`scripts/run-w5.sh`）：用 `$!` 记下自己起的 serve.sh 的 pid（`setsid` 不 fork，serve.sh 最后 `exec python`，pid 不变；已在远端用 `sleep` 模拟验证），用 `kill -0` 判活；启动前若仍有 sglang/serve.sh 进程则拒绝启动；启动超时先清理自己起的进程。新增 `ONLY_BATCH3=1`，跳过批 1、2 直接跑批 3。未在真卡上验证，补跑本身即验证。

## 2026-09-23 · 更正 W4「回撤全为 0」
- W4 结论 1 与 c8 超时分析里的「`num_retracted_reqs` 全为 0」读的是每周期清零的 gauge。按累计计数器 `num_retracted_requests_total`（`experiments/w4-*/report.md` 的 `retracted requests` 行）：w4-c1 0/0/0、w4-c2 0/0/0、w4-c4 1/4/4、w4-c4-timestamp 2/2/1、w4-c8 1/2/0。回撤输入 token 三次合计 c4 237k、c4-timestamp 141k、c8 79k，是同组驱逐 token 的 1.6% / 0.26% / 0.28%。baseline-c1/c3、W3 全部 run 为 0。
- W5 已完成的 run：w5-c4-tail 第 3 次回撤 2 个请求，w5-c4-truncate 第 3 次回撤 1 个，其余为 0。
- 定性结论「退化来自驱逐 + 排队」不变；「回撤从未发生」「预期的 retraction 未发生」撤回。口径见 `docs/decisions.md` 2026-09-23。

## 2026-09-23 · experiments/w5-*（W5 三批）— 各 3 次完成
- 环境：RTX 4090 · sglang 0.5.20 · Qwen/Qwen3-8B-FP8 · pi 0.85.1 · replayer `8bc97bcf`（clean）。批 1、2 同一 server session（lpm，2026-09-22 09:25 → 23:28）；批 3 由 `ONLY_BATCH3=1 scripts/run-w5.sh` 补跑，lpm、fcfs 各自冷启动（2026-09-23 08:48 lpm ready 50 s；11:33 fcfs ready 70 s，起前显存 0 MiB），链路 14:46 按设计关机。2026-09-22 的启动竞态修复在真卡上验证通过。
- `out/` 已拉回本地；`just resummarize` 七组 21 个 run（远端 replayer 早于 `b0af394`，summary 里没有 `server_delta`），再 `just report` / `just compare`。每组第 1 个 run 的 `metrics_before` 缺 `sglang:evicted_tokens_total`（冷启动后计数器尚未出现、不在 `LAZY_COUNTERS` 里），按缺失处理：**w5-control、w5-c8-lpm、w5-c8-fcfs 的驱逐量是 n=2**。
- `run-batch.sh` 日志里 w5-c8-lpm 三次都标 `FAILED`：`replay.run` 在 `n_errors > 0` 时返回 1（`replay/run.py:136`）。三次都跑完并写了 summary，错误全是 `ReadTimeout`（2 / 5 / 2），按右删失计入分位。服务端 `/v1/chat/completions` 的 HTTP 400 增量也是 2 / 5 / 2。
- 结果（`compare-*.md`，n=3，Δ 相对对照组；Δ/噪声 < 2× 的项不下结论）：
  - **批 1 · w5-tail vs w5-control（c1/real）**：命中 0.9620 vs 0.9633（与 `estimate.md` 的预测逐位一致）；TTFT P50 +3.8%（3.1×），TTFT P95/P99、单轮 P50/P95/P99 全在噪声内（≤ 1.6×，|Δ| ≤ 1.2%）；驱逐 +2.7%（985k vs 959k）。**时间戳移到 messages 末尾后，timestamp 改写的代价（W3：命中 0.1059、单轮 P95 +7.7%、TTFT P95 +1078.7%）消失。**
  - **批 2 · w5-c4-tail vs w5-c4（c4/real）**：命中 0.7688 vs 0.7467（1.0×）、驱逐 −8.2%（1.0×）、TTFT P95/P99、单轮各分位全在噪声内；只有 TTFT P50 −8.1%（2.2×）、wall −2.9%（3.7×）。**并发下 tail 与 identity 无可分辨差异**（负面结果，也是预期结果：tail 本来就不该有代价）。
  - **批 2 · w5-c4-truncate vs w5-c4**：命中 0.8801 vs 0.7467（+17.9%，6.1×）；TTFT P50 −32.6%、**P95 −81.7%**（14259 → 2613 ms）、P99 −78.0%；单轮 P50 −50.8%、**P95 −29.5%**、P99 −25.5%；prompt tokens −29.2%（13.78M vs 19.47M）；驱逐 −63.4%（1.90M vs 5.18M）；wall −31.5%。全部 ≥ 6.1×。对比 W3（c1/compressed）truncate 命中 −5.5 点、单轮 P95 −7.1%：c4 下符号翻转，命中反而 +13 点。
  - **批 3 · w5-c8-fcfs vs w5-c8-lpm（c8/real，只差 `--schedule-policy`）**：命中 0.1991 vs 0.5293（−62.4%，14×）；驱逐 15.90M vs 9.11M（+74.5%，n=2）；TTFT P50 **+285.1%**（4682 → 18027 ms）、P95 +39.7%（3.6×）、**P99 −73.4%**（249443 → 66417 ms，5.3×）；单轮 P50 +141.7%、P95 +3.4%（1.7×，噪声内）、**P99 −57.5%**；wall +16.7%；超时 0/0/0 vs 2/5/2（1.7×）。按 `requests.jsonl`：最大 TTFT fcfs 71 / 77 / 76 s，lpm 592 / 382 / 587 s；TTFT > 120 s 的请求 fcfs 0/0/0，lpm 16/11/15。回撤 fcfs 2/2/2，lpm 1/0/0。
- lpm 的超时形态与 W4-c8 相同：三次都在同一条长轨迹 `20260918T114524` 上相邻两轮连续超时（turn 43–44、35–36、39–40），run 2 另有 3 个是不同轨迹的 turn 0。
- fcfs 三次几乎逐位可复现：run 2 与 run 3 驱逐 15895056 vs 15895055、回撤输入 token 都是 71633、wall 相差 1 s。
- 同组复跑一致性（replayer 版本不同，只作一致性检查，不同表）：w5-c4 命中 0.7467 ± 0.0217 vs w4-c4 0.7520 ± 0.0054；w5-c8-lpm 0.5293 vs w4-c8 0.5309，TTFT P95 36821 vs 37104 ms。w5-c4 这次噪声更大（命中 CV ~2.9%，TTFT P95 ± 1480 ms），批 2 里 tail 的「噪声内」判定部分受此影响。
- 结论：
  1. **头条 remedy 成立**：不是「别给模型时间」，是「别放在前缀里」。时间戳放 messages 末尾时，c1 下命中只差 0.0013、延迟全在噪声内；c4 下与 identity 无可分辨差异。
  2. **LPM 饥饿回路（findings 7）有了对照支持**：换 fcfs 后 ≥ 600 s 的超时和成对超时都消失，TTFT 最大值从 ~590 s 降到 ≤ 77 s。代价是驱逐 +75%、命中 0.53 → 0.20、中位 TTFT ×3.9——一个真实的 trade-off，不是哪个策略全面更好。单轮 P95 两者在噪声内。饥饿发生在哪条轨迹上的机制解释仍是推断，数据只到超时分布与调度器计数器。
  3. **并发下缩短上下文的收益被放大**：truncate 在 c1 下主要省 decode（单轮 P95 −7.1%，命中略降）；在 c4 下总 prompt 少 29%，驱逐少 63%，命中反升 13 点，TTFT P95 −82%。机制推断：KV 池（W4：78k token）能同时装下更多会话的前缀。这一组同时改变了负载本身（token 量），不是纯缓存效应，不能拿它的命中率去和 identity 讲「缓存更好」。
