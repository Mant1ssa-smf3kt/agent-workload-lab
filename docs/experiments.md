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
