# 结论汇总

W3 + W4 的结论合在一处。每个数字都能在 `experiments/*/report.md`、`compare-*.md` 或 `out/*/summary.json` 里找到；逐次实验的完整记录在 [experiments.md](experiments.md)，口径与取舍在 [decisions.md](decisions.md)。

环境（全部实验相同）：RTX 4090 24 GB 单卡 · SGLang 0.5.20（radix cache、`--schedule-policy lpm`、chunked-prefill 8192、KV 池 78384 token）· Qwen3-8B-FP8（YaRN×2 → 65536）· pi 0.85.1 录制的 25 条 coding-agent trajectory（837 请求/轮，prompt P50 21.5k token，输出 P50 114 token）· 每组配置重跑 3 次。

## 头条

> harness 在 system prompt 末尾写入当前时间，使 radix cache 命中率从 **0.9633** 降到 **0.1059**，单轮 P95 延迟上升 **7.7%**（TTFT P95 上升 **1078.7%**，507 → 5971 ms）；改为 append-only 组装后恢复到 0.9633。
> —— 单并发，`experiments/w3-timestamp/compare-w3-control.md`

同一个改写在 4 条轨迹同飞时：命中率 0.7520 → 0.0981，单轮 P95 **+36.7%**，TTFT P50 **+1045.6%**（`experiments/w4-c4-timestamp/compare-w4-c4.md`）。

## 数据

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/w3-transforms-dark.png">
  <img alt="W3: four context transforms at single concurrency" src="figures/w3-transforms.png">
</picture>

| W3 · c=1 · compressed | cache hit | TTFT P50 / P95 / P99 (ms) | 单轮 P50 / P95 / P99 (ms) | prompt tok | wall (s) |
|---|---|---|---|---|---|
| append-only (control) | 0.9633 | 236 / 507 / 852 | 2352 / 22813 / 39842 | 19.47M | 4624 |
| system_timestamp | **0.1059** | 2306 / **5971** / 7668 | 5550 / 24577 / 41619 | 19.49M | 6615 |
| tools_rotate | 0.3150 | 1231 / 5951 / 7684 | 5237 / 24076 / 41128 | 19.47M | 6244 |
| truncate_tool_results | 0.9102 | 240 / 695 / 1006 | 2267 / **21194** / 39231 | **13.78M** | 4413 |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/w4-concurrency-dark.png">
  <img alt="W4: concurrency sweep with the timestamp transform at c=4" src="figures/w4-concurrency.png">
</picture>

| W4 · real timing | cache hit | TTFT P50 / P95 / P99 (ms) | 单轮 P50 / P95 / P99 (ms) | 驱逐 tok/次 | 队列非空 | 超时 | wall (s) |
|---|---|---|---|---|---|---|---|
| c=1 | 0.9633 ± 0.0000 | 240 / 506 / 856 | 2350 / 22710 / 39765 | 0.96M | 0% | 0 | 5958 |
| c=2 | 0.9626 ± 0.0001 | 261 / 544 / 1643 | 2548 / 23973 / 41092 | 0.97M | 1.6% | 0 | 3175 |
| c=4 | 0.7520 ± 0.0054 | 428 / **13107** / 27845 | 6100 / 37269 / 64770 | 5.1M | 49% | 0 | 2792 |
| c=8 | 0.5309 ± 0.0155 | 4674 / 37104 / 223480 | 10561 / 70486 / 231259 | 9.3M | 82% | **11** | **3237** |
| c=4 + system_timestamp | **0.0981** ± 0.0002 | 4907 / 18061 / 45842 | 10891 / 50959 / 92756 | **17.8M** | 52% | 0 | 4167 |

c=8 的分位含 11 个按右删失计入的超时请求（客户端 600 s 放弃，真实值更大；`decisions.md` 2026-09-21）。CV：c=8 的 P99 为 14–17%，其余 ≤ 4.8%。

## 结论

按「数据直接支持」到「数据一致但含推断」排序。

### 1. 过了缓存容量之后，加并发让吞吐倒退

wall：c1 5958 s → c2 3175 → c4 2792 → **c8 3237**（+15.9%，6.4× 噪声）。同样 19.4M prompt token，c8 比 c4 多花 16% 墙钟、多 9.3M 驱逐 token 的重复 prefill、丢了 11 个请求。普通 LLM serving 的直觉是「并发加到算力饱和为止」；agent 负载的吞吐最优并发是**缓存装得下的并发**，过线后每个指标都变差。c8 的 wall 含超时等待，但把 timeout 调大只会等更久，方向不变。

### 2. 压力全部由驱逐吸收，回撤一次都没发生

15 个 run `sglang:num_retracted_reqs` 全为 0，包括队列 82% 时间非空的 c8。原因在负载形状：输出 P50 只有 114 token，运行中请求的 KV 增长可忽略；池子里塞满的是**空闲会话的缓存前缀**（工具执行间隙里的那些）。调度器永远有可驱逐的叶子，就永远不需要回撤。agent 负载下 KV 池实际上是一个会话缓存，决定尾延迟的是 LRU 驱逐，不是为回撤准备的那些旋钮。

佐证：c≥4 时驱逐量 ≈ 未命中量——c4 5.0–5.2M vs (1−0.752)×19.47M = 4.83M；c8 9.0–9.6M vs 9.09M；c4-timestamp 17.83M vs 17.58M。每一个被驱逐的 token 都被某个活着的会话重新 prefill 了一遍。

### 3. 命中率是个糟糕的延迟预测器

同一套 trace：truncate 命中 −5.5 点、单轮 P95 **−7.1%**；c1→c4 命中 −21 点、TTFT P95 **+2488%**；c4→c4-timestamp 再 −65 点、TTFT P95 只再 **+38%**。前 21 点的损失是排队引起的（排在别人的冷 prefill 后面，队列非空 0% → 49%），后 65 点只是把已经在排队的人的 prefill 拉长。该报的量是**未命中的 token 量与队列占用**，不是命中率百分比。

### 4. 截断旧工具结果让单轮延迟变好，是因为 decode 变快了

truncate 的 TTFT P95 变差（+37.3%，前缀失配），但单轮 P95 变好（−7.1%）。输出长度按录制固定（`output_mode: recorded`），能解释这个剪刀差的只有更短的上下文让每个 decode step 更便宜（15k vs 22k token 的 attention）。「上下文管理」的收益主要落在长输出轮次的 decode 上，不是省 prefill。

### 5. 命中率变得不可复现，本身就是过了悬崖的信号

同配置同 seed 三次重跑，hit std：c1 0.0000、c2 0.0001、c4 0.0054、c8 0.0155。单并发下命中率是字节级确定的；一旦并发导致驱逐，命中率取决于各会话工具间隙到达的墙钟顺序。同配置下 hit rate 抖动，先查是不是在互相挤，再查 harness。

### 6. harness 侧的改动可以离线评估单租户命中率，但并发代价评估不了

W1 本地按 chat template 算的相邻请求共享前缀 P50 0.980，实测 c1 命中 0.9633；W3 三个 transform 的本地预估 0.110 / 0.110 / 0.983，实测 0.106 / 0.315 / 0.910，方向全对。但 timestamp 的真实代价从 c1 的单轮 P95 +7.7% 变成 c4 的 +36.7%，这一段只能上 GPU 测。tokenize + LCP 守第一道门；第二道门必须带并发。

### 7. LPM 调度下有「富者愈富」的饥饿回路（机制含推断）

c8 的 11 个超时里 6 个在同一条 125 请求的长轨迹上**成对**出现（turn 34 等 600 s 超时，turn 35 紧接着再等 600 s），3 个是某个 run 的首请求，其中一条是 1675 token 的冷启动——理论上最便宜的请求等了 10 分钟以上。`num_requests_total` 差值（839 − 超时数）说明这些请求在服务端被干净 abort，不是泄漏。

推断：8 条 20k+ 的会话总 footprint ≥ 160k，远超 78k 的池子，任何会话只要停下来做一次工具调用，回来时前缀已被驱逐；LPM 按匹配前缀长度排序，它于是排到所有热会话后面，排着队时前缀也不会刷新，下一轮依然最后。冷启动只有 1 例，方向性证据。后续实验见 `later.md`（`--schedule-policy fcfs` 对照）。

### 8. 悬崖位置 ≈ KV 池 / 单会话上下文，与算力无关（含推断）

78384 token 的池子，会话最大 prompt P50 25.4k，装得下 ≈ 3 条；实测 c2 无事（驱逐 0.97M，与 c1 持平）、c4 出事（5.1M）。没有 c3 数据，只能说悬崖在 2 与 4 之间、与 78k/25k 一致。容量规划应按「并发会话数 × 上下文长度 ≤ KV 池」算：一张 24 GB 卡跑 8B FP8，agent 并发上限是个位数。

## 边界

- 一张卡、一个模型、一个 serving 框架、一种 harness。数字不外推到其他配置；方向性结论（1–6）依赖的是负载形状（长 prompt、短输出、有间隙），应当可迁移，但未验证。
- W3 用 compressed 时序、W4 用 real 时序，两组数字不同表。W4-c1 与 W3-control 各分位差 ≤ 1.7%，支持单并发下二者等价。
- c8 的 P99 CV 14–17%，只下方向性结论。
- trace 未公开（含第三方仓库代码与模型输出），复现需自行录制；trace 的 sha256 与形状见 `experiments/profile/meta.json` 与 `profile.md`。
