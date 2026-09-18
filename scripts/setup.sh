#!/usr/bin/env bash
# 远端环境装配。幂等；无卡模式即可运行（不需要 GPU）。
#
#   bash scripts/setup.sh            # 全部：serve venv + 项目 venv + 模型权重
#   bash scripts/setup.sh --no-model # 跳过权重下载
#
# 不要在开卡状态下跑这个脚本（下载大文件按小时计费）。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
source "$HERE/env.sh"

WANT_MODEL=1
[[ "${1:-}" == "--no-model" ]] && WANT_MODEL=0

log() { printf '{"ts":"%s","step":"%s","msg":"%s"}\n' "$(date -Is)" "$1" "$2" >&2; }

# ── 0. 驱动检查（无卡模式下 nvidia-smi 可能不存在，跳过；有卡时不满足直接退出） ──
if command -v nvidia-smi >/dev/null 2>&1; then
  DRV="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1 || true)"
  if [[ -n "$DRV" && "$DRV" -lt "$SGLANG_MIN_DRIVER" ]]; then
    log driver "host driver $DRV < $SGLANG_MIN_DRIVER required by sglang $SGLANG_VERSION; use SGLANG_VERSION=0.5.10 SGLANG_MIN_DRIVER=525"
    exit 1
  fi
  log driver "host driver ${DRV:-unknown} (need >= $SGLANG_MIN_DRIVER for sglang $SGLANG_VERSION)"
else
  log driver "nvidia-smi absent (no-GPU mode); driver check deferred to serve.sh"
fi

# ── 1. SGLang 服务 venv ───────────────────────────────────────────────────
log serve-venv "python: $(python3 --version 2>&1)"
if [[ ! -x "$SERVE_VENV/bin/python" ]]; then
  python3 -m venv "$SERVE_VENV"
fi
"$SERVE_VENV/bin/pip" install -q -i "$PIP_INDEX_URL" --upgrade pip
if ! "$SERVE_VENV/bin/python" -c "import sglang, sys; sys.exit(0 if sglang.__version__ == '$SGLANG_VERSION' else 1)" 2>/dev/null; then
  log serve-venv "installing sglang[all]==$SGLANG_VERSION"
  "$SERVE_VENV/bin/pip" install -i "$PIP_INDEX_URL" "sglang[all]==$SGLANG_VERSION"
fi
"$SERVE_VENV/bin/pip" install -q -i "$PIP_INDEX_URL" "modelscope==$MODELSCOPE_VERSION"
log serve-venv "sglang $("$SERVE_VENV/bin/python" -c 'import sglang; print(sglang.__version__)')"

# ── 2. 项目 venv（replay / metrics / analysis） ───────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  log project-venv "installing uv"
  pip install -q -i "$PIP_INDEX_URL" uv
fi
# 用机器上已有的 3.11+ 解释器，避免 uv 去 GitHub 下 python（国内网络）。
PROJECT_PY=""
for cand in python3.12 python3.11 python3.13; do
  if command -v "$cand" >/dev/null 2>&1; then PROJECT_PY="$(command -v "$cand")"; break; fi
done
[[ -n "$PROJECT_PY" ]] || { log project-venv "no python3.11+ on PATH; install one (conda create -n py312 python=3.12)"; exit 1; }
( cd "$REMOTE_DIR" && UV_INDEX_URL="$PIP_INDEX_URL" UV_PYTHON_DOWNLOADS=never uv sync --group dev --python "$PROJECT_PY" )
log project-venv "ok ($PROJECT_PY)"

# ── 3. 模型权重（ModelScope） ─────────────────────────────────────────────
if [[ "$WANT_MODEL" == 1 ]]; then
  mkdir -p "$MODELS_DIR"
  if [[ -f "$MODEL_DIR/config.json" ]]; then
    log model "present: $MODEL_DIR"
  else
    log model "downloading $MODEL_ID → $MODEL_DIR"
    "$SERVE_VENV/bin/modelscope" download --model "$MODEL_ID" --local_dir "$MODEL_DIR"
  fi
  sha256sum "$MODEL_DIR/config.json" | awk '{print $1}' > "$MODEL_DIR/.config.sha256"
fi

mkdir -p "$FINGERPRINT_DIR"
log done "serve venv: $SERVE_VENV · model: $MODEL_DIR"
