# agent-workload-lab

刻画 coding agent 负载对 LLM 推理服务的压力，验证 harness 侧上下文组装策略如何影响 serving 侧的缓存与调度。工作约定见 [CLAUDE.md](CLAUDE.md)。

```
pi + extension/  ──录制──▶  traces/*.jsonl  ──replay/──▶  SGLang (AutoDL 单卡)
                                 │                              │
                          analysis/profile              metrics/ + artifact
                          (W1 负载画像)               experiments/<name>/out/<run>/
```

| 目录 | 内容 |
|---|---|
| `extension/` | pi extension：录制每次 provider 请求的原样 payload、时序、工具耗时（TS，`npm test` / `npm run smoke`） |
| `analysis/` | trace 加载与负载画像表（`just profile`） |
| `replay/` | replayer：trace → 归一化 payload 序列 → 按并发与时序打到 SGLang，落盘 artifact |
| `metrics/` | SGLang `/metrics` 抓取 |
| `scripts/` | AutoDL 装配 / 起服务 / 指纹 / 同步 / 录制 |
| `experiments/` | 每个实验 `config.yaml`（schema 在 `replay/config.py`）+ `out/`（不入库） |
| `docs/` | `decisions.md` 决策、`experiments.md` 实验日志、`recording.md` 录制 runbook、`later.md` |

```bash
just test / just lint                          # 本地，无 GPU
bash scripts/record.sh <repo> <case>           # 录一条 trajectory
just profile                                   # 画像表 → experiments/profile/out/
just replay-dry baseline-c1                    # 无卡：构建重放计划
bash scripts/serve.sh && just replay baseline-c1   # 远端，需要开卡
```
