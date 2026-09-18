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
