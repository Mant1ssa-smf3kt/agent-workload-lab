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

## 每条 trajectory

```bash
cd <目标仓库>
pi --model zai/glm-5.2:off        # thinking off，见下
```

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

## 录完检查

```bash
just profile                 # → experiments/profile/out/profile.md
```

看三件事：`请求 outcome` 里 `done` 占绝大多数；`每条 trace` 表里没有 `reqs (done)` 为 0 的行；`tools 定义在相邻请求间变化的次数` 为 0（否则说明 pi 在会话中途改了工具集，属异常）。

画像表本身就是 W1 的交付物，放进 `experiments/profile/`（`out/` 不入库，`profile.md` 复制一份到 `experiments/profile/profile.md` 提交）。
