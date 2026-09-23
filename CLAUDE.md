# CLAUDE.md

本文件是本仓库的工作约定。任何在此仓库中工作的 agent 在动手前先读完，并严格遵守「硬性约束」与「实验纪律」两节。

---

## 1. 这个项目是什么

**agent-workload-lab** —— 刻画 coding agent 负载对 LLM 推理服务的压力，并验证 harness 侧的上下文组装策略如何影响 serving 侧的缓存与调度表现。

一句话链路：

```
pi (coding agent harness)
  └─ 录制真实 trajectory（云端强模型，一次性）
       └─ replayer 以可控并发重放到本地 SGLang
            └─ 采集 radix cache 命中 / TTFT / 队列深度 / batch 组成
                 └─ 改 harness 侧上下文组装策略，测 before/after
```

项目要产出的**头条结论**（报告第一句话，形状固定，数字待测）：

> harness 侧某个看似无害的上下文改写，使 radix cache 命中率从 A 降到 B，单轮 P95 延迟上升 C%；改为 append-only 组装后恢复到 D。

所有工作都服务于把这句话里的 A/B/C/D 填成可复现的真数字。

---

## 2. 非目标

以下内容**明确不做**，不要主动提议、不要顺手实现：

- **不写 CUDA / 不做算子优化。** 本项目全部工作在调度、缓存、服务化与 harness 层。
- **不追任务成功率。** 重放阶段用小模型，任务做没做对与本项目无关。评价对象是 **trace 的形状与时序**，不是答案质量。
- **不做 LLM judge、不做答案打分。** 生态里已有（`@artale/pi-eval` 等），不重复造。
- **不做通用 dashboard。** 产出是可复现的数字与图表文件，不是 Web UI。
- **第一阶段不引入 Dynamo。** 单实例 SGLang 足够体现缓存与调度现象。Dynamo 的 `agent_context` / `agent_hints` 只作为接口设计参考。若第四周有余力再议，需显式确认。
- **不重写 pi。** pi 当黑盒，只在两个位置介入：上下文拼装处、模型请求发出处。

---

## 3. 目录结构

```
extension/      TypeScript。pi extension，录制 trajectory 与轮次级事件
replay/         Python。workload replayer：读 trajectory，按并发与时序重放
metrics/        Python。SGLang 指标抓取与归一化
analysis/       Python。出表出图（report / plot），生成报告片段
experiments/    每个实验一个目录：config.yaml + 结果 artifact + 环境指纹
traces/         录制的 trajectory（**不入库**，见 .gitignore）
scripts/        AutoDL 环境装配、服务起停、本地↔远端同步
docs/           findings.md 结论汇总、experiments.md 实验日志、decisions.md 决策、figures/ 出图、later.md
```

**语言分工**：只有 `extension/` 是 TypeScript（因为 pi 是 TS）。其余全部 Python。不要在 Python 侧引入 Node 依赖，反之亦然。

---

## 4. 核心概念

| 术语 | 定义 |
|---|---|
| **trajectory** | 一个完整 agent 会话的请求序列。含每轮的完整 prompt、工具调用与输出、轮间时间间隔、输出长度。录制后**只读**。 |
| **replay** | 把 trajectory 作为负载重放到本地推理服务。只保真 token 序列与时序，不保真模型行为。 |
| **保真模式** | `timing=real` 按原始轮间隔重放；`timing=compressed` 去掉工具执行空窗，压力测试用。两种模式的数字不可互相比较。 |
| **实验** | 一次 `experiments/<name>/` 下的完整运行，必须自带 config、artifact、环境指纹三件套。 |

---

## 5. 指标定义（口径固定，不得随意更改）

改动任何一条定义都必须在 `docs/decisions.md` 记录，并重跑受影响的全部基线。

- **prefix cache 命中率** = 命中的 prefill token 数 / 总 prefill token 数。按请求聚合，不按会话。
- **TTFT** = 请求发出到收到第一个内容 token 的墙钟时间。含排队。
- **单轮延迟** = 一轮 agent turn 的端到端时间，需拆成三段上报：模型时间 / 工具执行时间 / harness 开销。三段之和与总时长的差额也要记录。
- **尾延迟** 一律报 P50 / P95 / P99，**禁止只报均值**。客户端超时（`timeout_s`）的请求按右删失计入分位，不得剔除；落在删失值上的分位标 `≥`（`docs/decisions.md` 2026-09-21）。
- **上下文增长** = 每轮 prompt token 数随轮次的曲线。
- **跨轮共享前缀比例** = 相邻两轮 prompt 的最长公共前缀 token 数 / 后一轮 prompt token 数。

---

## 6. 环境与开发流程

**开发在本地，执行在远端。永远不要在服务器上写代码。**

- 本地：写代码、用 AI 工具、跑单元测试、做分析出图。
- AutoDL 无卡模式：装依赖、拉模型权重、跑 replayer 的 dry-run、调通链路。
- AutoDL 有卡模式：**只在真正采集延迟数字时开**。跑完立刻落盘 artifact 并关机。

同步用 `scripts/sync.sh`（rsync，单向本地→远端，排除 `traces/` 与 `experiments/*/out/`）。

国内网络：pip 走国内源，模型权重用 ModelScope 拉。不要在开卡状态下下载大文件。

---

## 7. 常用命令

```bash
# 本地
just test            # 单元测试，不需要 GPU
just lint            # 格式与类型检查
just report EXP      # 从 experiments/EXP/out/ 生成报告片段
just compare EXP CTL # 对照表（校验指纹一致、只动一个变量）
just plot            # docs/figures/ 出图 + 同名 csv
just resummarize EXP # summary 口径变更后从 requests.jsonl 重算
just estimate EXP [CTL] # 第一道门：真模板 + 真 tokenizer 估计单租户命中率，不需要 GPU → experiments/EXP/estimate.md

# 远端（无卡模式即可）
bash scripts/setup.sh         # 幂等，装依赖 + 拉权重
just replay-dry EXP           # 不连推理服务，只验证 trajectory 解析与调度逻辑

# 远端（需要开卡，谨慎执行）
bash scripts/serve.sh         # 起 SGLang。参数见脚本内注释
just replay EXP               # 正式重放，落盘 artifact
```

> agent 注意：标记「需要开卡」的命令**不得自动执行**，必须先向人确认。这些命令按小时计费。

---

## 8. 硬性约束

1. **`traces/` 与 `experiments/*/out/` 永不入库。** 只提交 config 和生成出来的表格/图。
2. **录制好的 trajectory 是只读的。** 任何清洗、过滤、裁剪都必须产生新文件并在 config 里记录来源与处理方式，不得原地修改。
3. **版本锁死。** pi、SGLang、模型权重、replayer 自身的 commit，全部写进每次实验的环境指纹。跨版本的数字不得放进同一张对比表。
4. **不得编造数字。** 报告、README、注释里出现的每个数字，都必须能在某个 `experiments/*/out/` 的 artifact 里找到来源。没跑出来就写 TBD，不要填占位值，也不要用「大约」「预计」蒙混。
5. **只在人明确要求时 push**（`origin/master`；仓库公开）。push 前检查待推送的提交不含 `traces/`、`experiments/*/out/`、`scripts/remote.env` 与任何密钥或远端地址。不得创建 PR。
6. **改 pi 源码前先停下来问。** 优先用 extension、provider、环境变量解决；确实需要改内部时，先说明改哪两处、为什么 extension 做不到。

---

## 9. 实验纪律

- **每个实验必须自带环境指纹**：GPU 型号、驱动、SGLang 版本与启动参数、模型与量化方式、pi 版本、replayer commit、时间戳。缺一项的 artifact 视为无效。
- **方差先于结论。** 任何一组对比数字，在下结论前必须同配置重跑三次并报告方差。如果噪声幅度接近或超过改进幅度，结论作废，先解决噪声。
- **一次只动一个变量。** 对照组之间除了被测项，其余配置必须逐字节相同（含随机种子、并发数、trajectory 集合与顺序）。
- **负面结果照样记录。** 改了没效果是有价值的结论，写进 `docs/experiments.md`，不要删掉重来。

---

## 10. 代码约定

- Python 3.11+，类型标注齐全，`ruff` + `mypy` 过关。
- 所有可调参数进 config，不写死在代码里。config 用 YAML，schema 在 `replay/config.py`。
- 指标采集失败**不得让实验崩掉**：记录为缺失值并在 artifact 里显式标记，继续跑完。
- 日志用结构化 JSON 行，不用 print。
- 不引入重型依赖（没有 pandas 以外的数据框架，没有实验管理平台，没有 ORM）。

---

## 11. 路线与当前状态

- [x] **W1 打通与刻画** — 环境脚本、pi 指向本地端点、录制 20–30 条 trajectory、产出 agent 负载画像表
- [x] **W2 replayer 与基线** — replayer 可用、SGLang 指标接入、单并发与多并发基线、方差确认
- [x] **W3 改进与头条数字** — 上下文组装策略对照组，填满第 1 节那句话的 A/B/C/D
- [x] **W4 并发与收尾** — 尾延迟退化、缓存驱逐、长 trajectory 饥饿；报告与可复现脚本

当前状态：**W1–W4 实验全部完成；结论汇总在 `docs/findings.md`，README 已重写为结果优先。** W1：25 条 trajectory（`docs/recording-tasks.md` + `scripts/record_batch.py` 自动录制）、画像表 `experiments/profile/`。W2：AutoDL 4090 + sglang 0.5.20 跑通，baseline-c1/c3 各三次方差成立（`experiments/baseline-c*/report.md`）。W3：四组各三次跑完（`experiments/w3-*/report.md`、`compare-w3-control.md`），头条数字已填（`docs/decisions.md` 2026-09-20）：timestamp 改写使命中率 0.9633 → 0.1059，单轮 P95 +7.7%，TTFT P95 +1078.7%；append-only 为 0.9633。W4：`w4-c{1,2,4,8}` 并发扫描 + `w4-c4-timestamp` 各三次（`experiments/w4-*/report.md`、`compare-*.md`，`docs/experiments.md` 2026-09-21）：悬崖在 c2→c4（命中 0.963 → 0.752，TTFT P95 506 → 13107 ms），c8 命中 0.531、11 个请求排队 ≥ 600 s 超时（按右删失计入），回撤罕见（c4 每 run ≤ 4 次、c1/c2 为 0，按累计计数器；2026-09-23 更正了「全为 0」）；timestamp 改写在 c4 下单轮 P95 +36.7%（c1 下为 +7.7%）。不补 c3、不做 hint 实验（`docs/decisions.md` 2026-09-21）。

**W5（2026-09-22/23，已完成、实例已关）**：`experiments/w5-*` 三批各 3 次（`docs/experiments.md` 2026-09-23，`docs/findings.md`）。批 1 头条 remedy：时间戳移到 messages 末尾，`w5-tail` 命中 0.9620 vs `w5-control` 0.9633（与 `just estimate` 一致），延迟除 TTFT P50 +3.8% 外在噪声内。批 2：c4 下 tail 与 identity 噪声内无差异；truncate 命中 0.7467 → 0.8801、TTFT P95 −81.7%。批 3：fcfs 消除 lpm 的超时（0 vs 2/5/2），代价是命中 0.5293 → 0.1991、TTFT P50 +285.1%。W5 的 replayer 为 `8bc97bcf`，只与 W5 自带对照组同表。任何 harness 侧改写先过 `just estimate`。

> W3 的结论是本项目的核心，不可裁剪。时间紧张时优先砍 W4 的 hint 实验。
