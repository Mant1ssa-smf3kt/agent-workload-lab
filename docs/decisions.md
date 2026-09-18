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
