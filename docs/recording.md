# 录制 runbook（W1）

目标：20–30 条真实 coding-agent trajectory，落在 `traces/`，只读。

## 一次性准备

1. 云端模型走 OpenAI-compatible provider（`docs/decisions.md` 2026-09-18）。pi 内置的 `zai`（GLM）已满足：
   `api: openai-completions`、`system` 角色、`max_tokens`、无 `store`。payload 里会多 `thinking` 与 `tool_stream` 两个字段，replayer 负责剥掉。
   其他内置的国内 OpenAI-compatible provider（`deepseek`、`moonshotai-cn`、`qwen-token-plan-cn`、`minimax-cn`）同样可用；**一批录制只用一个 provider + 一个模型**，混用会让 `usage` 口径不一致。
2. **把录制模型的上下文窗口压到与重放侧一致**：把 `scripts/pi-models.recording.json` 的内容写成 `~/.pi/agent/models.json`
   （这个文件默认不存在，新建即可；`scripts/pi-models.example.json` 是连同 sglang provider 的完整版）。
   **不要改 `~/.pi/agent/models-store.json`**——那是 pi 自动拉取的目录缓存（有 `checkedAt`/`etag`），会被覆盖。
   验证：`pi --list-models | grep glm-5.2` 应显示 `65.5K  8.2K`。
   pi 的 compaction 触发条件是 `contextTokens > contextWindow − 16384`（`reserveTokens` 默认值）。GLM-5.x 的窗口是 1M，
   不覆盖的话录制时永远不会自然 compaction，而且轨迹会长到塞不进 SGLang 的 `--context-length 65536`。
   覆盖成 65536 后，compaction 会在 ~49k token 处触发——这正是重放侧会遇到的形状。
3. 让 pi 常驻加载 extension，免得每次敲 `-e`：
   ```json
   // ~/.pi/agent/settings.json
   { "extensions": ["/Users/mant1ssa/Projects/ClawEval/extension/src/index.ts"] }
   ```
   默认落盘到本仓库 `traces/`（extension 按自身路径推导）；也可 `AWL_TRACE_DIR=… ` 或 `--trace-dir …` 覆盖。
4. 确认链路：`cd extension && npm run smoke`。

## 自动录制（推荐）

```bash
uv run python scripts/record_batch.py --pending          # 把 docs/recording-tasks.md 里还没录的任务全部录完
uv run python scripts/record_batch.py t06 t07 --dry-run  # 只看计划
```

驱动脚本用 pi 的 RPC 模式：每条任务一个 pi 进程（worktree 隔离、extension + `zai/glm-5.2:off` 固定），按文档里的 prompt 顺序发送，
等 `agent_settled` 后随机等 20–45 s 再发下一个（模拟人类思考间隔），最后关 stdin 让 `shutdown` 落盘。任务与 prompt 直接从
`docs/recording-tasks.md` 解析（`### tNN · 仓库` 标题、`record.sh` 行、引用块），文档是唯一来源。已录的任务按 trace header 的 cwd 识别。

## 手动录制

```bash
bash scripts/record.sh <仓库路径> <用例名>          # 开 worktree + 启动 pi（extension、模型、thinking 固定）
bash scripts/record.sh <仓库路径> <用例名> --clean  # 录完删 worktree
```

`record.sh` 会从目标仓库 HEAD 分离检出一个 worktree 到 `~/awl-rec/<repo>-<用例名>`，agent 的改动都落在那里，不碰你的工作树；
启动前自检模型可用且 contextWindow 已覆盖为 65.5K，不满足直接退出。等价的手动命令是
`cd <worktree> && pi -e extension/src/index.ts --model zai/glm-5.2:off`。

- **thinking 关掉录第一批。** 开着时 pi 会把上一轮的 thinking 以 `reasoning_content` 写回历史 assistant 消息
  （zai 走 `clear_thinking: false`），prompt 会被 reasoning 文本撑大，形状偏离小模型重放。
  **glm-5.3 不支持关 thinking**（目录里 `thinkingLevelMap.off = null`，只有 low/high/max），所以用 glm-5.2。
  要研究 reasoning 对上下文增长的影响，另起一批、单独标注。
- 会话结束用 Ctrl-D / `/quit`，让 `session_shutdown` 触发，trace 才有 `shutdown` 记录。中途崩了也没关系——记录是逐条同步追加的，只是最后一个 request 会标成 `unfinished`。
- 一个 pi 会话 = 一条 trace = 一个文件。同一会话里多次输入（多个 run）是**期望的**：run 间的人类思考间隔是负载的一部分。
- 别改录出来的文件。要筛选、裁剪，产生新文件并在实验 config 里写来源与处理方式（CLAUDE.md §8.2）。

## 任务组合（目标：形状多样，不追求做对）

| 类型 | 数量 | 特征 |
|---|---|---|
| 读代码回答问题 | 5–6 | read/grep 密集，工具结果大，上下文增长快，输出短 |
| 小修 bug | 6–8 | read → edit → bash(test) 循环，中等轮数 |
| 新增功能 | 5–6 | 多文件 edit/write，长会话，可能触发 compaction |
| 重构/批量改 | 3–4 | 大量 edit，assistant 输出长 |
| 跑命令/排错 | 3–4 | bash 密集，工具耗时长，轮间隔大 |

跨 2–4 个不同规模的仓库；每条 5–40 轮；至少 3 条要长到触发 compaction（窗口覆盖为 65536 后约在 49k token 处触发），因为 compaction 是缓存失效的最大来源之一。

## 第一批用例（3 条，形状互补）

三个本地仓库正好覆盖三种形状。**任务不需要做对**（CLAUDE.md §2），要的是轨迹形状；但 prompt 要像真实需求，agent 才会认真多轮干活。
每个用例录 2 遍（`case1a` / `case1b`），同一 prompt 的两次轨迹差异就是录制侧的天然方差。

### 用例 1 · 读代码回答 — `minimind`（read/grep 密集，输出短，单 run）

```bash
bash scripts/record.sh ~/Projects/minimind case1a
```

首个 prompt（原样粘贴）：

> 我想搞清楚这个仓库里 GRPO 和 PPO 两条训练路径的区别。请读 trainer/train_grpo.py、trainer/train_ppo.py 和 trainer/rollout_engine.py，回答：(1) 两者的 rollout 是怎么产生的，SGLangRolloutEngine 和 TorchRolloutEngine 各在什么条件下被选用；(2) reward 计算和优势估计分别在哪一行、公式是什么；(3) 两者共享了 trainer_utils 里的哪些函数。给出文件名和行号，不要改任何代码。

第二个 prompt（等它答完再发，制造 run 间隔）：

> 如果我想把 PPO 也接到 SGLang rollout 上，最少要动哪几处？只列改动点，不要写代码。

预期形状：8–15 轮，几乎全是 `read`/`grep`，工具结果大（整文件），assistant 文本短；`每轮 prompt 增量` 由工具结果主导。

### 用例 2 · 改代码 + 跑测试循环 — `Learn-OpenClaw`（edit/bash 密集，多 run，轮间隔大）

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw case2a
# worktree 里没有 .venv；第一个 prompt 里让 agent 自己 uv sync
```

首个 prompt：

> 给 core/memory.py 的 Memory 类补一套 pytest 测试，放在 tests/test_memory.py，覆盖 add_message、build_context 和 compress 三个方法，compress 至少要有一个「压缩后 token 数确实低于阈值」的断言。项目用 uv 管理，先 uv sync，pytest 不在依赖里就加进 dev 依赖。跑到全部通过为止。

第二个 prompt：

> compress 现在是怎么决定丢哪些消息的？我觉得它可能会把 system 消息也丢掉，写一个能复现这个问题的测试，如果真有问题就修掉。

第三个 prompt：

> 把你改的地方用 git diff 给我看一遍，然后 commit，message 用英文。

预期形状：15–30 轮，`bash` 占比高且耗时分散（uv sync 几十秒、pytest 几秒），`edit`/`write` 多；三个 run 之间有你读输出的思考间隔。

### 用例 3 · 跨包功能，长会话 — `reactive-resume`（读得多、上下文最长，目标触发 compaction）

```bash
bash scripts/record.sh ~/Projects/reactive-resume case3a
```

首个 prompt：

> 我要给简历加一个「期望薪资」字段（expectedSalary，字符串，可选）。请从 packages/schema 的简历 schema 开始，贯通到 apps/web 里 basics 那一节的编辑表单、packages/pdf 的渲染，以及任何导入/导出会碰到这个字段的地方。先用 grep 把所有需要改的位置列出来给我确认，再动手。注意：这台机器没装依赖，不要 pnpm install，不要跑 build 或 test，改完告诉我哪些文件改了、每处改了什么。

它列完清单后回复：

> 可以，全部改。

改完再发一个 prompt 把会话拉长：

> 再检查一遍 i18n：这个字段的 label 在 lingui 的翻译目录里需要加条目吗？需要的话把 zh-CN 和 en 都加上。

预期形状：25–40 轮，`grep`/`read` 结果巨大（monorepo），prompt 在十几轮内冲到 40k+，**应当出现 ≥1 次 `compaction`**——`profile.md` 的「每会话 compaction 次数」不为 0 才算达到目的；没触发就继续追加 prompt（如「把 docx 导出也加上」）。

### 三条录完看什么

`just profile` 后对照：

| 用例 | 该看的行 | 期望 |
|---|---|---|
| 1 | 工具混合 | `read`/`grep` 占绝大多数，`edit`/`write` 为 0 |
| 2 | 工具时间 / 轮 P95、人类思考间隔 n | 工具 P95 ≥ 数秒；思考间隔 n = 2 |
| 3 | 每会话 compaction 次数、最大 prompt tokens | compaction ≥ 1；最大 prompt 接近 49k |
| 全部 | 请求 outcome、警告 | 全 `done`，无警告 |

形状符合再按上面的任务组合表扩到 20–30 条。

## 录完检查

```bash
just profile                 # → experiments/profile/out/profile.md
```

看三件事：`请求 outcome` 里 `done` 占绝大多数；`每条 trace` 表里没有 `reqs (done)` 为 0 的行；`tools 定义在相邻请求间变化的次数` 为 0（否则说明 pi 在会话中途改了工具集，属异常）。

画像表本身就是 W1 的交付物，放进 `experiments/profile/`（`out/` 不入库，`profile.md` 复制一份到 `experiments/profile/profile.md` 提交）。
