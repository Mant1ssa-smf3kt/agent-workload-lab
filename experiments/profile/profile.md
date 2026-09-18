# Agent 负载画像（录制侧）

来源：3 条 trace · api=openai-completions · model=zai/glm-5.2 · pi=0.85.1

所有数字为 P50 / P95 / P99 (n)。
时序为录制侧（云端模型 + 真实工具），只描述负载形状，不与重放侧比较。
`prompt_tokens` = provider 上报的 input + cacheRead，是云端 tokenizer 口径。

> **警告**
> - skipped 20260918T112808.996_01a0b446-1cf4-755d-81cc-42bc16e7447c.jsonl: 0 requests < --min-requests 1

## 会话形状

| 指标 | P50 / P95 / P99 (n) |
|---|---|
| 每会话轮数 | 41 / 124 / 124 (n=3) |
| 每会话请求数 | 41 / 124 / 124 (n=3) |
| 每会话工具调用数 | 41 / 158 / 158 (n=3) |
| 每会话 compaction 次数 | 0 / 1 / 1 (n=3) |
| 会话墙钟 | 460.8 s / 1037.3 s / 1037.3 s (n=3) |
| 会话活跃时间 (Σ turn) | 286.0 s / 942.5 s / 942.5 s (n=3) |

## 上下文

| 指标 | P50 / P95 / P99 (n) |
|---|---|
| 首轮 prompt tokens | 1599 / 4487 / 4487 (n=3) |
| 末轮 prompt tokens | 28978 / 40130 / 40130 (n=3) |
| 最大 prompt tokens | 28978 / 48972 / 48972 (n=3) |
| 每请求 prompt tokens | 28978 / 43492 / 48534 (n=172) |
| 每轮 prompt 增量 tokens | 327 / 1558 / 4890 (n=169) |
| payload 大小 | 120682 chars / 185945 chars / 205968 chars (n=172) |
| payload 消息数 | 103 / 189 / 202 (n=172) |
| 跨轮共享前缀比例 (chars, messages JSON) | 0.988 / 0.996 / 0.998 (n=169) |
| 跨轮相同前导消息数 | 103 / 187 / 200 (n=169) |
| tools 定义在相邻请求间变化的次数 | 0 |

## 时序

| 指标 | P50 / P95 / P99 (n) |
|---|---|
| TTFB（响应头） | 3148 ms / 5398 ms / 20804 ms (n=172) |
| TTFT（首个内容 delta，不含 thinking） | 3148 ms / 5399 ms / 20804 ms (n=172) |
| 模型时间 / 请求 | 3828 ms / 19622 ms / 33201 ms (n=172) |
| 单轮总时长 | 4436 ms / 23621 ms / 45185 ms (n=172) |
| 工具时间 / 轮（区间并集） | 18 ms / 13070 ms / 16801 ms (n=172) |
| harness 开销 / 轮（直接测量） | 5 ms / 8 ms / 22 ms (n=172) |
| 未归因 / 轮（总 − 三段） | 0 ms / 0 ms / 0 ms (n=172) |
| 请求间隔（上一请求结束 → 下一请求发出） | 25 ms / 13530 ms / 46106 ms (n=169) |
| 人类思考间隔（run 间） | 24508 ms / 67855 ms / 67855 ms (n=4) |

## 输出

| 指标 | P50 / P95 / P99 (n) |
|---|---|
| output tokens / 请求 | 104 / 1160 / 2009 (n=172) |
| 文本输出 | 63 chars / 1739 chars / 4434 chars (n=172) |
| thinking 输出 | 0 chars / 0 chars / 0 chars (n=172) |
| 工具调用数 / 请求 | 1 / 3 / 4 (n=172) |
| 请求 outcome | {"done": 172} |
| stop_reason | {"toolUse": 165, "stop": 7} |

## 工具混合

| 工具 | 次数 | 错误 | 耗时 P50 / P95 / P99 |
|---|---|---|---|
| bash | 118 | 5 | 42 ms / 13367 ms / 16801 ms (n=118) |
| read | 60 | 2 | 3 ms / 6 ms / 8 ms (n=60) |
| edit | 27 | 2 | 6 ms / 18 ms / 19 ms (n=27) |
| write | 2 | 0 | 3 ms / 6 ms / 6 ms (n=2) |

## 每条 trace

| trace | model | runs | turns | reqs (done) | tools | compact | wall s | prompt tokens first→last (max) |
|---|---|---|---|---|---|---|---|---|
| 20260918T113328.991_01a0b44a-feed-7319-8d81-26bc60993dec.jsonl | zai/glm-5.2 | 2 | 7 | 7 (7) | 8 | 0 | 199.2 | 1599→19460 (19460) |
| 20260918T113724.590_01a0b44e-9741-7681-9e28-7be8696fbe2e.jsonl | zai/glm-5.2 | 3 | 41 | 41 (41) | 41 | 0 | 460.8 | 1598→28978 (28978) |
| 20260918T114524.746_01a0b455-eadd-7017-a2d0-d234d8dbcb0c.jsonl | zai/glm-5.2 | 2 | 124 | 124 (124) | 158 | 1 | 1037.3 | 4487→40130 (48972) |
