# 决策记录

每条决策：日期、决定了什么、为什么、影响面。改指标口径的决策必须同时列出需要重跑的基线。

---

## 2026-09-18 · 录制阶段走 OpenAI-compatible API，不走 Anthropic Messages API

**决定**：录制 trajectory 时，pi 通过 `openai-completions` 类 provider 调用云端强模型（DeepSeek / Qwen / Kimi 等任何 OpenAI 兼容端点均可）。不用 `anthropic-messages`。

**为什么**：extension 把 provider payload 原样落盘（`request.payload`）。SGLang 的 `/v1/chat/completions` 与 OpenAI-compatible 云端点是同一种 wire 格式，重放时除 `model` 字段外可以字节级复用 `messages` / `tools`，不需要在 replayer 里重新实现 pi 的消息序列化逻辑，也就不引入「重放 prompt 与录制 prompt 不一致」这一层误差。

**影响**：
- `replay/` 直接消费 `request.payload`，只替换 `model`、`stream_options`、采样参数。
- 录制 runbook 中 pi 的 provider 必须是 `api: "openai-completions"`；trace header 的 `model.api` 字段可用于校验，`analysis/` 遇到非 `openai-completions` 的 trace 应拒绝或显式标记。
- 不同云端模型的 tokenizer 与本地重放模型不同，**录制侧 `usage.input` 的 token 数不能与重放侧数字放进同一张表**；跨轮共享前缀比例等 token 口径指标一律用重放模型的 tokenizer 在 payload 上重算。

## 2026-09-18 · trace 文件格式 v1

**决定**：`extension/src/schema.ts` 中 `TRACE_SCHEMA_VERSION = 1`。一个 pi session 一个 JSONL；`request` 记录内联完整 payload；`context` 记录只存每条消息的 sha256 与长度摘要。

**为什么**：payload 是 serving 侧的 ground truth，必须完整；`context` 与 payload 内容重复，只保留足以在相邻两轮之间定位「哪条消息被改写」的摘要。磁盘换简单性——traces 不入库。

**影响**：任何破坏性改动需升 schema 版本并在此追加记录；旧 trace 不迁移，标注 schema 版本后隔离。

## 2026-09-18 · 重放模型与服务版本锁

**决定**：`scripts/env.sh` 锁定 `sglang==0.5.20`、`modelscope==1.40.1`、重放模型 `Qwen/Qwen3-8B-FP8`（ModelScope），tool-call parser `qwen25`、reasoning parser `qwen3`。GPU 目标：AutoDL 单卡 RTX 4090 (24GB)，5090 (32GB) 备选。

**为什么**：
- 单卡 24GB 上 bf16 8B 只剩 ~6GB 给 KV cache（≈40k token），装不下多条并发的长 agent 上下文，radix cache 实验无从谈起；FP8 权重 ~8GB，KV 可达 ~14GB。
- Qwen3 在 SGLang 里工具调用与 reasoning parser 都是一等支持，减少链路调试。
- 0.5.20 是写下这条时 PyPI 上的最新版；选最新是为了 5090 的 Blackwell 支持。

**影响**：改任何一项 = 换实验环境，已有基线作废，跨版本数字不得同表（CLAUDE.md §8.3）。`scripts/fingerprint.sh` 把这些值写进每次 serve 的指纹。

## 2026-09-18 · 录制第一批 thinking 关闭，模型用 glm-5.2

**决定**：录制用 `zai/glm-5.2:off`。

**为什么**：zai 的 thinking 开启时以 `clear_thinking: false` 发送，pi 会把上一轮 thinking 以 `reasoning_content` 写回后续轮的 assistant 历史消息（pi-ai `openai-completions.js`），使 prompt 形状偏离小模型重放时的形状。先拿干净的基线。glm-5.3 的 `thinkingLevelMap.off` 为 `null`，不能关 thinking，因此选 glm-5.2（`off → "none"`）。

**影响**：需要 reasoning 对上下文增长影响的结论时，另录一批、在 config 里标注，不与第一批混表。

## 2026-09-18 · 录制模型的 contextWindow 覆盖为重放侧的 context-length

**决定**：录制时通过 `~/.pi/agent/models.json` 的 `modelOverrides` 把云端模型的 `contextWindow` 设为 65536（= `scripts/serve.sh` 的 `CONTEXT_LENGTH` 默认值），`maxTokens` 设为 8192（`scripts/pi-models.recording.json`，已用 `PI_CODING_AGENT_DIR` 隔离目录验证 `--list-models` 显示 65.5K / 8.2K）。

**为什么**：pi 在 `contextTokens > contextWindow − reserveTokens(16384)` 时 compaction。glm-5.3 窗口 1M，不覆盖则永远不 compaction，轨迹长度也不受重放服务上下文上限约束。compaction 是本项目要观察的主要缓存失效来源之一，录制侧必须能自然触发。

**影响**：`CONTEXT_LENGTH` 与这里的覆盖值必须同步改；trace header 的 `model.context_window` 字段应等于 65536，`analysis/` 可据此校验。

## 2026-09-18 · replayer 保真口径

**决定**（`replay/trajectory.py`、`replay/config.py`）：
1. 只重放 `outcome == done` 的请求；superseded/aborted/error 的没有 usage 与 t_end，丢弃并计入 `dropped_requests`。
2. payload 原样转发 `messages / tools / stream / max_tokens` 等通用键，剥掉 provider 私有键（zai：`thinking`、`tool_stream`；OpenAI：`store`），`model` 换成重放模型，`developer` 角色改 `system`。剥掉的键写进 fingerprint。
3. 输出长度：`max_tokens` = 录制侧 `usage.output`，并发 `ignore_eos: true`，让 decode 长度精确等于录制值，与小模型「想说什么」无关。录制侧是 GLM tokenizer 口径，token 数与 Qwen 有偏差，但两侧一致偏差不影响对照。
4. 时序：`gap_before_ms` = 上一请求 `t_end` → 本请求 `t_request`（含工具时间与人类思考）。`timing=real` 按 `gap_scale` 缩放、`max_gap_s` 封顶；`timing=compressed` 全部为 0。
5. compaction 摘要调用：录制侧拿不到 payload（见 later.md），按 `compaction.usage.input` 从上一请求消息前缀切出等量字符 + 一条 summarize 指令合成，`max_tokens = usage.output`，标记 `synthetic: true`；summary 同时报含/不含合成请求两组数。
6. Qwen3 经 `chat_template_kwargs.enable_thinking=false` 关 thinking（`server.extra_body`），与录制侧 thinking off 对齐。

**为什么**：CLAUDE.md §4——只保真 token 序列与时序，不保真模型行为。以上每一条都是把「模型行为」从变量里拿掉。

**影响**：改任何一条都是换保真口径，跨口径数字不得同表。summary 里 `cache_hit_rate = Σcached_tokens / Σprompt_tokens`（§5，按请求聚合），`cache_hit_per_request` 只是辅助分布。


## 2026-09-18 · serve.sh 加 `--enable-cache-report`

**决定**：SGLang 启动参数加 `--enable-cache-report`。

**为什么**：读 0.5.20 源码（`srt/entrypoints/openai/protocol.py` `UsageInfo`）：`prompt_tokens_details.cached_tokens` 只在该开关打开时返回。不开则 replayer 拿不到每请求的命中 token 数，§5 的 `cache_hit_rate` 无法按请求聚合，只能退化成 `/metrics` 的全局 `sglang:cache_hit_rate`。

**影响**：无性能副作用已知；它进入指纹的 `serve_args`。`ignore_eos`、`chat_template_kwargs` 亦已在同一文件确认为 `ChatCompletionRequest` 合法字段。

## 2026-09-18 · 重放服务用 YaRN 把 Qwen3-8B 扩到 65536

**决定**：`serve.sh` 加 `--json-model-override-args '{"rope_scaling":{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":32768}}'`（factor 由 `CONTEXT_LENGTH / 32768` 算出）。

**为什么**：Qwen3-8B `config.json` 的 `max_position_embeddings=40960`，SGLang 0.5.20 拒绝 `--context-length 65536`（可用 `SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1` 硬闯，但无 RoPE 扩展）。录制侧 contextWindow 已定为 65536，且 reactive-resume 轨迹的 prompt 最高 ~49k token，40960 装不下。YaRN 是 Qwen3 官方的长上下文方式。

**影响**：YaRN 改变的是模型输出质量，不改变 prompt token 序列与调度；对本项目的指标无影响。它进入指纹 `serve_args`。若换 `CONTEXT_LENGTH`，factor 自动跟随。

## 2026-09-18 · serve.sh 关闭 prefill CUDA graph

**决定**：`--disable-prefill-cuda-graph`。decode CUDA graph 保持默认开启。

**为什么**：sglang 0.5.20 默认启用 breakable prefill CUDA graph；在 4090 + flashinfer（首次 JIT）下捕获阶段触发 torch 内部断言 `markCaptureEnd called with no captures in progress`，服务起不来。prefill graph 只影响 prefill 的绝对耗时，不影响缓存与调度行为；作为固定环境参数写进指纹即可。

**影响**：所有实验统一关闭；若日后打开，属于换环境，基线作废。


## 2026-09-19 · replayer v2：三处保真修正

**决定**：
1. 合成 compaction 请求保留 `tools`（`synthesize_compaction_payload`）。
2. `warmup_requests` 改为「第一条轨迹的前 N 步」，与并发无关。
3. `metrics.key_metrics` 对 `*_total` 计数器按 label 求和（SGLang 按 `is_streaming` 拆分）。

**为什么**：baseline-c1 实测合成 compaction 命中仅 0.197——Qwen3 chat template 把 tools 渲染在 system 段之后，去掉 tools 使前缀从 ~3.7k token 起失配；c1 vs c3 的 prompt tokens total 差 2740，是全局顺序 warmup 在并发下剔除了不同请求；`prompt_tokens_total` 只取到了非流式那一组 label。

**影响**：replayer 版本变了（指纹 replayer commit 不同），**baseline-c1/c3 的数字不能与之后的实验同表**；W3 用自己的控制组 `w3-control`（identity）。

## 2026-09-19 · W3 对照组设计：三种「看似无害」的上下文改写

**决定**（`replay/transforms.py`，配置 `experiments/w3-*`）：与 `w3-control`（identity）只差 `transform` 一项：
- `system_timestamp`：每个请求在 system prompt 末尾加「当前时间」（确定性时钟，重跑字节一致）。对应 harness 把日期/时钟写进 system prompt。
- `tools_rotate`：每个请求把 tools 列表轮转一位；工具集与语义不变。对应无序工具注册表、动态工具加载。
- `truncate_tool_results`（keep_recent 4 / max_chars 800）：滑动窗口截断旧工具结果。对应最常见的「上下文管理」优化。

**为什么选这三个**：本地按 chat template 顺序（system → tools → messages）算相邻请求共享前缀，identity 0.990、timestamp 0.110、tools_rotate 0.110、truncate 0.983——改头（system/tools）与改尾（旧工具结果）的差异是本项目要量化的核心；compaction（录制侧实测 0.14）已在轨迹里自然出现，不另做 transform。

**影响**：每组三次重跑；`analysis/report` 把 `transform` 子树当作一个变量比较。W3 使用全部 8 条 trace（223 步），与 baseline-c1 的 3 条不同，也不同表。

## 2026-09-19 · W3 用 `timing=compressed`

**决定**：`experiments/w3-*` 四个配置统一 `timing: compressed`（其余不变）。W4 的并发实验仍用 `real`。

**为什么**：W3 是单并发对照。间隔期间服务器空闲，radix cache 在 78k token 池、≤52k prompt 下无内存压力、不驱逐，因此命中率与 TTFT 与 real 模式一致，只是省掉全部工具/思考间隔（baseline-c1 里占 wall 的 ~30%）。完整 23 条 trace × 12 个 run 用 real 需 8–12 小时，compressed 可压到一个晚上。

**影响**：W3 数字不与 real 模式的 baseline-c1/c3 同表（本来就因 replayer 版本与 trace 集合不同表）。若日后做 W3 的并发版本，必须回到 real。

## 2026-09-20 · 头条数字 C 的口径：按 §5「单轮延迟」P95，TTFT P95 并列报告

**决定**：CLAUDE.md §1 那句话里的 C 填 **单轮延迟 P95 的相对涨幅**（§5 定义：一轮端到端时间，重放侧只有模型时间一段），即 timestamp vs control 的 **+7.7%**（22813 → 24577 ms，`experiments/w3-timestamp/compare-w3-control.md`）。同一句话紧跟 **TTFT P95 +1078.7%**（507 → 5971 ms）作为并列数字，不用 TTFT 冒充「单轮延迟」。

**为什么**：§5 已把「单轮延迟」定义为端到端，不能因为 TTFT 的数字更震撼就换口径。实测 P95 轮次由 decode 主导，prefill 5 s 的差额到 P95 只剩 7.7%；而 TTFT 是用户可感知的「开始出字」时间，P95 涨 10.8× 是真实的体验退化。两者各说一件事，都报。

**影响**：头条句固定为：「harness 在 system prompt 末尾写入当前时间，使 radix cache 命中率从 0.9633 降到 0.1059，单轮 P95 延迟上升 7.7%（TTFT P95 上升 1078.7%，507 → 5971 ms）；改为 append-only 组装后恢复到 0.9633。」（4090 · sglang 0.5.20 · Qwen3-8B-FP8 · 单并发 · compressed · n=3。）W4 若做多并发版本，C 的口径不变。

## 2026-09-21 · 超时请求按右删失计入尾延迟分位，不再剔除

**决定**：replayer 因 `server.timeout_s` 放弃等待的请求（`ReadTimeout` / `WriteTimeout`），其 TTFT / 单轮延迟按**右删失**计入分位：观测值 = 放弃等待时刻（≈ timeout_s），真实值只知 ≥ 它。`analysis.stats.pct_censored` 把删失值按其下界排序参与 nearest-rank；某分位的 rank 之内含删失值时，该分位标 `≥`（下界）。报告新增 `timeouts (censored)` 行；非超时错误（HTTP 4xx/5xx）仍剔除并阻塞判定。cache hit rate 口径不变（仍只按拿到 usage 的请求聚合）。已完成 run 用 `just resummarize EXP` 从 `requests.jsonl` 重算 `summary.json`，旧文件留作 `summary.prev.json`。

**为什么**：w4-c8 三次共 11 个请求在队列里等满 600 s 被客户端断开（`res_ttfb_ms` 为空，服务端连响应头都没发）。旧口径把它们当错误剔除，等于把最慢的 1.3% 样本删掉再算 P99——恰好是 W4 要测的「长轨迹饥饿」尾部。重算后 w4-c8 的 TTFT P99 从 132.5–176.1 s 变为 185.8–262.6 s，latency P99 从 177.3–181.7 s 变为 200.2–265.0 s；P50/P95 变化 ≤ 12%。不选择调大 timeout 重跑 c8：删失口径已能给出正确方向的界，且 GPU 已关（用户决定）。

**影响**：需重算的基线 = 所有 `experiments/*/out/`。实际只有 w4-c8 的数字变化；其余 12 个 W4 run 与 W3 / baseline 全部 0 错误，重算结果逐字节相同（已核对），已提交的报告数字不受影响。`summary.json` 新增 `timeout_s`、`n_timeouts`、`all.n_censored`、`*_ms.p{50,95,99}_censored`、`*_ms.max_censored`。CLAUDE.md §5 同步加一句。

## 2026-09-21 · W4 收尾范围：并发扫描 c1/c2/c4/c8 + c4 下的 timestamp 对照，不补 c3，不做 hint 实验

**决定**：W4 以 `experiments/w4-c{1,2,4,8}`（只动 concurrency）与 `w4-c4-timestamp`（只动 transform）五组各三次收尾。不补 c3，不重跑 c8，不做 Dynamo `agent_hints` 类实验。

**为什么**：c1→c2 各指标变化 ≤ 9%（TTFT P99 除外，Δ/噪声仅 2.2×），c2→c4 出现悬崖（TTFT P95 544 → 13107 ms，24×），c3 落在悬崖中间对结论帮助有限（用户判断）。c8 已观察到超时（饥饿），删失口径给出下界即可。hint 实验按 CLAUDE.md §11 属可砍项。

**影响**：W4 完成；报告的并发结论只覆盖 c ∈ {1,2,4,8}，不对 c3、c>8 外推。

## 2026-09-21 · 第一道门：真 chat template + 真 tokenizer 的单租户命中率估计（`just estimate`）

**决定**：新增 `analysis/estimate.py`。对一个实验 config，用与 `replay.run` 相同的加载、归一化、transform 与派发顺序取出全部 step，按 sglang 0.5.20 `/v1/chat/completions` 的真实路径渲染（HF `apply_chat_template(tokenize=False, add_generation_prompt=True, tools=…)` + `encode(add_special_tokens=False)`；list content 压成 `" ".join(text parts)`；`chat_template_kwargs` 取自 config 的 `server.extra_body`），用重放模型自己的 tokenizer 分词，把每个请求的命中 token 定义为与「同一轨迹上一请求」或「更早轨迹首请求」的最长公共前缀（c=1 顺序、不驱逐），另报「同一轨迹任意更早请求」的上界（缓存无限大）。输出 `experiments/<exp>/estimate.{json,md}`，入库；tokenizer 文件（11 MB）从 ModelScope 拉到 `~/.cache/agent-workload-lab/`，不入库。依赖新增 `jinja2`、`tokenizers`（轻量）。

**校准**（`experiments/*/estimate.json` vs 各 `out/*/summary.json`，均为 §5 口径 Σcached/Σprompt）：

| 实验 | 估计 | 上界 | 实测 | 差 |
|---|---|---|---|---|
| w3-control / w4-c1 | 0.9633 | 0.9633 | 0.9633 | ±0.0000 |
| w3-timestamp | 0.1064 | 0.1064 | 0.1059 | +0.0006 |
| w3-truncate | 0.9101 | 0.9101 | 0.9102 | −0.0001 |
| w3-tools-rotate | 0.1078 | 0.8657 | 0.3150 | 实测在估计与上界之间 |
| w4-c2 | 0.9633 | 0.9633 | 0.9626 | +0.0007 |
| w4-c4 / w4-c8 / w4-c4-timestamp | 0.9633 / 0.9633 / 0.1064 | — | 0.7520 / 0.5309 / 0.0981 | 并发差额，估计器按 c=1 |

timestamp 组的 prompt token 增量估计 +20,925，与实测 +20,925 逐 token 相等。W1 的字符级估计（`profile.py`，messages JSON 的 LCP）偏 1.7 个点，本估计器偏 ≤ 0.07 个点。

**为什么**：findings §6 已把「tokenize + LCP 守第一道门」写成结论，但仓库里只有字符级版本，且它看不见 chat template 把 tools 渲染在 system 段内这类细节。有了逐 token 精确的第一道门，任何 harness 侧改写都能先在本地拿到命中率预测再决定是否花 GPU（W5 各组的预测见 `experiments/w5-*/estimate.md`）。

**适用边界**：
- 只估计命中率，不估计 TTFT / 单轮延迟；不建模驱逐与并发（w4-c4/c8 的差额就是并发代价，只能上 GPU）。
- 有周期的改写（tools_rotate）会重新命中更早的分支，实测落在「上一请求」估计与「任意更早请求」上界之间，估计器只给区间。
- 估计的 Σprompt 比实测少 ~0.5%：合成 compaction 请求的长度按录制 usage 合成，与服务端实际分词有偏差；不影响命中率的对照。

**影响**：`just estimate EXP [CTL]`；`analysis/estimate.py` 的口径改动需在此追加记录并重跑全部 `estimate.json`。

## 2026-09-21 · W5 规划：头条 remedy 的可执行形式、并发下的验证、LPM 饥饿的对照

**决定**：新增八个实验目录（`experiments/w5-*`），分三批，每批自带重跑的控制组，GPU 时间按已有 run 的 wall 估计：

| 批 | 实验 | 只动的变量 | 检验 | 预测 | GPU |
|---|---|---|---|---|---|
| 1（c1 / compressed） | `w5-control`、`w5-tail`、可选 `w5-after-tools` | transform | 头条 D 的可执行形式：时间戳信息不变、位置从 system prompt 末尾移到 messages 末尾（每轮替换） | 命中 0.9620（estimate）；after_tools 0.1406 | ~8 h（+3.9 h 可选） |
| 2（c4 / real） | `w5-c4`、`w5-c4-tail`、`w5-c4-truncate` | transform | tail 在并发下是否仍无代价（预期 Δ ≤ 噪声，按 §9 记为等价性结论）；缩 29% 上下文能否把 c4 推回悬崖之内（结果不可预知） | tail ≈ 0.752；truncate 0.75–0.91 | ~7 h |
| 3（c8 / real） | `w5-c8-lpm`、`w5-c8-fcfs` | server `--schedule-policy`（指纹 `serve_args`，config 逐字节相同） | findings 7「LPM 饥饿回路」由推断变数据：fcfs（sglang 0.5.20 出厂默认）是否消除 ≥ 600 s 成对超时、代价多少命中率 | 超时消失、命中率下降 | ~5.5 h |

**为什么每批重跑控制组**：replayer commit 已过 `d77ffcc`（删失聚合、resummarize、transforms 新位置），`analysis/report` 的 `env_key` 含 replayer commit，新 run 与 W3/W4 老 run 不得同表（§8.3）。`d77ffcc..HEAD` 的 `replay/` diff 不碰请求路径，但按 commit 判、不按判断；顺带验证新 server session 能否复现 0.9633 / 0.752。头条句引用两张表（W3 的 control→head、W5 的 control→tail），各自对照自己的控制组，head 与 tail 不进同一张表。

**tail 的形态**：主跑 `position: tail`（每轮替换，ephemeral reminder），不是 `tail_append`（持久化在历史里）——前者与 head 的 prompt token 逐请求几乎相等（+29 vs +25 tok），是更干净的单变量对照；`tail_append` 会让 prompt 多 2.9% 且旧戳计入分子。措辞用「前缀保持」，不用「append-only」硬套。

**server 端变量的工具支持**：`analysis/report.py` 把指纹 `serve.serve_args` 解析成 `serve.<flag>` 变量：同一实验内各 run 必须一致；对照时与 config 差异一起计数，恰好一个可下结论，零个打「同配置重跑」，`--host/--port` 忽略。此前 compare 对 fcfs 这类实验会报「零差异」。

**不做**：`--mem-fraction-static`/`--max-total-tokens` 缩池子——池子下限受最长请求约束（重放侧 max prompt 52,715 + 输出 4,339 ≈ 53.4k，sglang `max_req_len = min(context_len−1, max_total_num_tokens−1)`），可行的最小池子 ≈ 54–56k 恰在 c2 同飞和（45.5–55.4k）的边界上，效应小且解释力弱；`--kv-cache-dtype fp8_e5m2`（池子 ≈ 157k）先需 ~10 分钟开卡验证 4090 兼容，且 dtype 改变 attention kernel、延迟不与 bf16 同表，只比缓存类指标需 ~5 h、全套 ~23 h，列为可砍；并发 c16 与换卡不做（c8 已删失、换环境基线作废）。

**影响**：GPU 前的准备已全部完成（transform 位置、report 工具、configs、dry-run、estimate）；开卡按批向人确认。批 3 需要用 `SCHEDULE_POLICY=fcfs bash scripts/serve.sh` 重启服务，与 lpm 组不能放在同一个 run-batch。

## 2026-09-22 · W5 砍掉 after_tools；全部批次自动串行运行，结束关机

**决定**：删除可选组 `experiments/w5-after-tools`（transform 代码里的 `position: after_tools` 与其单测保留）。W5 其余七个实验由 `scripts/run-w5.sh` 在远端一次性自动串行运行，不再逐批确认；批 1（`w5-control`、`w5-tail`）已由人于 2026-09-22 09:11 启动，脚本等它结束后接批 2、批 3，全部跑完自动 `shutdown`（AutoDL 关机脚本，停止计费）。

**为什么砍 after_tools**：它的结果是一个可以从第一道门直接算出的比值——命中 ≈ 可缓存头部（system 文本 + tools 块）/ 当轮 prompt。`estimate.json` 的 per-trajectory 数据：头部为常数（本负载 1.6k 或 4.4k tok，对应两种 system prompt 长度；tools 块 25 条轨迹全部落在 545–817 tok），命中随平均 prompt 从 3k → 33k 单调由 0.449 降到 0.134，按桶 <8k 0.237、8–20k 0.145、≥20k 0.136。c1 下 W3 四组的估计与实测差 ≤ 0.0007，3.9 h 机时验证不出新信息。「头内部换位置救不回来」这个结论的前提是 tools 块 ≪ 历史；若 harness 的 tools 块达 10–30k tok（大量 MCP 工具），结论要重看——记入 findings 的适用边界，不用 GPU 证。

**批 3 的启动方式**：`w5-c8-lpm` 与 `w5-c8-fcfs` **各自冷启动 server**（先重启 lpm 跑 lpm 组，再重启 fcfs 跑 fcfs 组），而不是 lpm 组沿用批 1/2 的热 session——让 `--schedule-policy` 成为两组之间唯一差异，缓存起点也对称。批 2 沿用批 1 的 session（同 W3/W4 做法：一个 session 内连跑）。

**影响**：CLAUDE.md §11 状态更新；§7「需要开卡的命令不得自动执行」对本次 W5 链视为已一次性确认。结果拉回后按批出 `report.md` / `compare-*.md`，写入 `docs/experiments.md`。
