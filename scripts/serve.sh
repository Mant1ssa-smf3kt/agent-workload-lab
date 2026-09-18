#!/usr/bin/env bash
# 起 SGLang。【需要开卡，按小时计费。agent 不得自动执行，必须先向人确认。】
#
#   bash scripts/serve.sh                      # 前台运行，Ctrl-C 停
#   bash scripts/serve.sh --disable-radix-cache  # 追加参数原样透传给 sglang（对照组用）
#
# 起服务前先写指纹到 $FINGERPRINT_DIR/serve-<ts>.json，并把路径打印到 stderr；
# replayer 读最新一份写进 artifact。指纹里的 serve_args 就是这里的最终参数。
#
# 与实验相关的旋钮（全部可用环境变量覆盖）：
#   CONTEXT_LENGTH     模型上下文上限。agent 轨迹常见 30k–100k，默认 65536
#   MEM_FRACTION       静态显存占比；FP8 8B 在 24GB 上 0.85 留 ~14GB 给 KV
#   CHUNKED_PREFILL    chunked prefill 大小；影响长 prompt 的排队与 TTFT
#   SCHEDULE_POLICY    lpm = longest-prefix-match（radix cache 友好，默认）/ fcfs
#   EXTRA_ARGS         其他参数
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
source "$HERE/env.sh"

CONTEXT_LENGTH="${CONTEXT_LENGTH:-65536}"
MEM_FRACTION="${MEM_FRACTION:-0.85}"
CHUNKED_PREFILL="${CHUNKED_PREFILL:-8192}"
SCHEDULE_POLICY="${SCHEDULE_POLICY:-lpm}"

[[ -f "$MODEL_DIR/config.json" ]] || { echo "model not found: $MODEL_DIR (run scripts/setup.sh)" >&2; exit 1; }
DRV="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1 || true)"
if [[ -n "$DRV" && "$DRV" -lt "$SGLANG_MIN_DRIVER" ]]; then
  echo "host driver $DRV < $SGLANG_MIN_DRIVER required by sglang $SGLANG_VERSION (see docs/remote.md)" >&2; exit 1
fi
[[ -x "$SERVE_VENV/bin/python" ]] || { echo "serve venv missing: $SERVE_VENV (run scripts/setup.sh)" >&2; exit 1; }

ARGS=(
  --model-path "$MODEL_DIR"
  --served-model-name "$MODEL_ID"
  --host "$SGLANG_HOST" --port "$SGLANG_PORT"
  --context-length "$CONTEXT_LENGTH"
  --mem-fraction-static "$MEM_FRACTION"
  --chunked-prefill-size "$CHUNKED_PREFILL"
  --schedule-policy "$SCHEDULE_POLICY"
  --tool-call-parser "$TOOL_CALL_PARSER"
  --reasoning-parser "$REASONING_PARSER"
  --enable-metrics                       # Prometheus /metrics：cache hit、队列、batch 组成
  --log-requests-level 0
  --random-seed 0
)
# shellcheck disable=SC2206
[[ -n "${EXTRA_ARGS:-}" ]] && ARGS+=($EXTRA_ARGS)
ARGS+=("$@")

mkdir -p "$FINGERPRINT_DIR"
FP="$FINGERPRINT_DIR/serve-$(date +%Y%m%dT%H%M%S).json"
bash "$HERE/fingerprint.sh" "${ARGS[@]}" > "$FP"
echo "fingerprint: $FP" >&2
ln -sfn "$FP" "$FINGERPRINT_DIR/serve-latest.json"

exec "$SERVE_VENV/bin/python" -m sglang.launch_server "${ARGS[@]}"
