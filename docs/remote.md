# 远端 runbook（AutoDL）

开发在本地，执行在远端；永远不要在服务器上写代码（CLAUDE.md §6）。下面每一步都在**本地**终端发起。

## 0. 一次性

```bash
cp scripts/remote.env.example scripts/remote.env   # 填 AutoDL 控制台的 SSH host / port
```

租实例时选 **RTX 4090 (24GB)**，先用**无卡模式**开机。镜像只要有 Python 3.11/3.12；镜像自带的 torch / CUDA toolkit 无所谓，
sglang 的配套 torch 会装进独立的 `venv-serve`。

**真正的硬约束是宿主机 NVIDIA 驱动**（容器里改不了；4090/5090 是消费卡，没有 forward-compat）：

| sglang | torch | CUDA 栈 | 宿主机驱动 |
|---|---|---|---|
| 0.5.20（默认锁定） | 2.13.0 | CUDA 13 | **≥ 580** |
| 0.5.10（cu12 最后一版） | 2.9.1 | CUDA 12.8 | ≥ 525（4090）/ ≥ 570（5090） |

租之前看 AutoDL 列表的「最高 CUDA 版本」：13.x 才能用默认锁；只有 12.x 的机器用
`SGLANG_VERSION=0.5.10 SGLANG_MIN_DRIVER=525 bash scripts/setup.sh`，并改 `scripts/env.sh` 默认值 + `docs/decisions.md` 记一笔。
`setup.sh` / `serve.sh` 都会先查 `nvidia-smi` 的驱动版本，不满足直接退出。

## 1. 无卡模式：装环境、拉权重、dry-run

```bash
bash scripts/sync.sh --traces                                   # 代码 + traces/ → 远端
ssh -p <PORT> root@<HOST> 'cd /root/autodl-tmp/agent-workload-lab && bash scripts/setup.sh'
#   幂等：venv-serve(sglang 0.5.20) + 项目 venv(uv) + ModelScope 拉 Qwen/Qwen3-8B-FP8（~8GB）
ssh -p <PORT> root@<HOST> 'cd /root/autodl-tmp/agent-workload-lab && uv run python -m replay.run experiments/baseline-c1/config.yaml --dry-run'
```

dry-run 输出 `plan` 行：trajectories=3 · steps=173 · synthetic=1 · dropped_keys=[thinking, tool_stream]。和本地一致就说明远端链路通了。关机。

## 2. 有卡模式：起服务、跑基线（按小时计费）

开两个 ssh 窗口。

**窗口 A（服务）**
```bash
cd /root/autodl-tmp/agent-workload-lab && bash scripts/serve.sh
#   先落指纹 /root/autodl-tmp/fingerprints/serve-latest.json，再 exec sglang。
#   等到日志出现 "The server is fired up and ready to roll!" 再进窗口 B。
```

**窗口 B（重放）**
```bash
cd /root/autodl-tmp/agent-workload-lab
curl -s localhost:30000/v1/models | head -c 200          # 确认 served model = Qwen/Qwen3-8B-FP8
uv run python -m replay.run experiments/baseline-c1/config.yaml      # 第 1 次
uv run python -m replay.run experiments/baseline-c1/config.yaml      # 第 2 次
uv run python -m replay.run experiments/baseline-c1/config.yaml      # 第 3 次（§9：方差先于结论）
```

每次 run 的最后一行日志有 `cache_hit_rate` / `ttft_p50_ms` / `errors`。errors ≠ 0 先看 `out/<run>/requests.jsonl` 的 `res_error`。

> 三次重跑之间**不要重启 sglang**——radix cache 是热的，这正是基线要测的状态；要测冷启动另开实验并在 config `notes` 里写明。

跑完 baseline-c4 同样三次，然后 **Ctrl-C 窗口 A，关机**。

## 3. 拉回、出报告

```bash
bash scripts/sync.sh --pull baseline-c1
bash scripts/sync.sh --pull baseline-c4
just report baseline-c1            # → experiments/baseline-c1/report.md（方差表 + 判定）
just report baseline-c4
just compare baseline-c1 baseline-c4   # → experiments/baseline-c1/compare-baseline-c4.md
```

`report.md` / `compare-*.md` 提交进仓库；`out/` 不入库。`report.md` 的「判定」行说「可用于对照」才算基线成立，否则先解决噪声。

## 预算参考

单条 trajectory 的重放时长 ≈ Σ(prompt 处理 + 输出 decode) + 间隔。`timing=real` 下 baseline-c1 的计划间隔总和是 368 s（`max_gap_s: 30` 封顶后，见 dry-run 的 `planned_gap_total_s`）；模型时间要上机才知道，第一次跑完把 `wall_s` 记到 `docs/experiments.md`。

## 常见问题

- `served model mismatch`：config 的 `server.model` 必须等于 `serve.sh` 的 `--served-model-name`（都取自 `scripts/env.sh` 的 `MODEL_ID`）。
- `serve fingerprint missing`：没跑 `serve.sh` 就直接 replay；或 config 的 `fingerprint` 路径不对。
- 显存不够（OOM at startup）：把 `MEM_FRACTION` 降到 0.80，或 `CONTEXT_LENGTH` 降到 49152；改了就要在 `docs/decisions.md` 记一笔，且之前的 run 不能同表。
