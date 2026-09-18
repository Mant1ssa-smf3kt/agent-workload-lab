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
- 第 3 次 run（`out/20260918T230558-partial`，97/173 请求）按用户要求中止，不计入
- 结论：**方差未确认**（只有 2 次完整 run，§9 要求 ≥ 3），但两次差异极小；基线数字先作参考，补第 3 次后再定。
- 待修：合成 compaction 请求去掉了 `tools`，而 chat template 把 tools 渲染进 system 段，导致该请求自身命中仅 0.197（预期 ~0.99）；W3 前改为保留 tools（见 later.md）
