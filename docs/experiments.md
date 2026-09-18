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
