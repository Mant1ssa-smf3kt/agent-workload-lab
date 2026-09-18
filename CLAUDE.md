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
analysis/       Python。出表出图，生成报告片段
experiments/    每个实验一个目录：config.yaml + 结果 artifact + 环境指纹
traces/         录制的 trajectory（**不入库**，见 .gitignore）
scripts/        AutoDL 环境装配、服务起停、本地↔远端同步
docs/           实验日志、决策记录、later.md
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
- **尾延迟** 一律报 P50 / P95 / P99，**禁止只报均值**。
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
5. **不得 push 到远程仓库**，不得创建 PR。本地提交即可。
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

- [ ] **W1 打通与刻画** — 环境脚本、pi 指向本地端点、录制 20–30 条 trajectory、产出 agent 负载画像表
- [ ] **W2 replayer 与基线** — replayer 可用、SGLang 指标接入、单并发与多并发基线、方差确认
- [ ] **W3 改进与头条数字** — 上下文组装策略对照组，填满第 1 节那句话的 A/B/C/D
- [ ] **W4 并发与收尾** — 尾延迟退化、缓存驱逐、长 trajectory 饥饿；报告与可复现脚本

当前状态：**W1 基本完成，W2 进行中。** 已完成：`extension/`（录制）、`analysis/profile.py`（画像表，已有 3 条真实 trace 的画像 `experiments/profile/`）、`scripts/`（AutoDL 环境，未上机）、`replay/` + `metrics/`（replayer 与 SGLang 指标接入，真实 trace dry-run 与假服务器全链路通过）。未做：录满 20–30 条、远端上机、基线与方差。

> W3 的结论是本项目的核心，不可裁剪。时间紧张时优先砍 W4 的 hint 实验。

---

## 12. 学习边界

**任何知识点，如果不是当前实验卡住的直接原因，就不学。** 冒出来的好奇心一律记进 `docs/later.md`，不要在工作时段展开。

agent 在回答问题时同样遵守这条：不要主动展开与当前任务无关的原理讲解。
