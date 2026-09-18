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

# ── 0.5 Python 自举：裸镜像可能没有 python。找不到 3.11+ 就从清华镜像装 Miniconda 到数据盘 ──
# 只接受 3.11–3.13：sglang/torch/flashinfer 按 Python 版本发编译 wheel，3.14 还没有（2026-09）。
# 非交互 ssh 不加载 ~/.bashrc，镜像自带的 conda 可能不在 PATH 里：把常见位置也搜一遍。
PY_CANDIDATES=(python3.12 python3.11 python3.13)
find_py() {
  for c in "${PY_CANDIDATES[@]}"; do command -v "$c" 2>/dev/null && return 0; done
  for d in "$REMOTE_ROOT/py312/bin" /root/miniconda3/bin /root/anaconda3/bin /opt/conda/bin; do
    for c in "${PY_CANDIDATES[@]}"; do [[ -x "$d/$c" ]] && { echo "$d/$c"; return 0; }; done
  done
  return 1
}
if ! PROJECT_PY="$(find_py)"; then
  CONDA_DIR="$REMOTE_ROOT/py312"
  log python "no python3.11–3.13; installing Miniconda(py312) from tuna → $CONDA_DIR"
  curl -fsSL -o /tmp/miniconda.sh "https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py312_26.7.1-1-Linux-x86_64.sh"
  bash /tmp/miniconda.sh -b -p "$CONDA_DIR" >/dev/null
  rm -f /tmp/miniconda.sh
  PROJECT_PY="$(find_py)" || { log python "bootstrap failed"; exit 1; }
fi
PY_VER="$("$PROJECT_PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
log python "$PROJECT_PY -> $PY_VER"

# ── 1. SGLang 服务 venv（解释器版本变了就重建） ─────────────────────────────
if [[ -x "$SERVE_VENV/bin/python" ]]; then
  VENV_VER="$("$SERVE_VENV/bin/python" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo none)"
  if [[ "$VENV_VER" != "$PY_VER" ]]; then
    log serve-venv "venv is python $VENV_VER, want $PY_VER; recreating"
    rm -rf "$SERVE_VENV"
  fi
fi
if [[ ! -x "$SERVE_VENV/bin/python3.$( "$PROJECT_PY" -c 'import sys; print(sys.version_info[1])')" && ! -x "$SERVE_VENV/bin/python" ]]; then
  "$PROJECT_PY" -m venv "$SERVE_VENV"
fi
# venv 里保证 bin/python 存在（并发/中断过的 venv 可能只剩 python3.X）
if [[ ! -x "$SERVE_VENV/bin/python" ]]; then
  PYX="$(ls "$SERVE_VENV"/bin/python3.* 2>/dev/null | head -1)"
  [[ -n "$PYX" ]] && ln -sf "$(basename "$PYX")" "$SERVE_VENV/bin/python"
  [[ -x "$SERVE_VENV/bin/python3" ]] || ln -sf "$(basename "$PYX")" "$SERVE_VENV/bin/python3"
fi
SV_PY="$SERVE_VENV/bin/python"
"$SV_PY" -m pip install -q -i "$PIP_INDEX_URL" --upgrade pip
have_sglang() { "$SV_PY" -c "import importlib.metadata as m, sys; sys.exit(0 if m.version('sglang') == '$SGLANG_VERSION' else 1)" 2>/dev/null; }
if ! have_sglang; then
  log serve-venv "installing sglang[all]==$SGLANG_VERSION"
  "$SV_PY" -m pip install -i "$PIP_INDEX_URL" "sglang[all]==$SGLANG_VERSION"
fi
"$SV_PY" -m pip install -q -i "$PIP_INDEX_URL" "modelscope==$MODELSCOPE_VERSION"
log serve-venv "sglang $("$SV_PY" -c 'import importlib.metadata as m; print(m.version("sglang"))') torch $("$SV_PY" -c 'import importlib.metadata as m; print(m.version("torch"))')"

# ── 2. 项目 venv（replay / metrics / analysis） ───────────────────────────
# uv 装在解释器同目录（非交互 ssh 的 PATH 可能不含它），用绝对路径调用
UV="$(command -v uv 2>/dev/null || true)"
if [[ -z "$UV" ]]; then
  UV="$(dirname "$PROJECT_PY")/uv"
  if [[ ! -x "$UV" ]]; then
    log project-venv "installing uv"
    "$PROJECT_PY" -m pip install -q -i "$PIP_INDEX_URL" uv
  fi
fi
[[ -x "$UV" ]] || { log project-venv "uv not found after install"; exit 1; }
# 用机器上已有的 3.11+ 解释器，避免 uv 去 GitHub 下 python（国内网络）。
( cd "$REMOTE_DIR" && UV_INDEX_URL="$PIP_INDEX_URL" UV_PYTHON_DOWNLOADS=never "$UV" sync --group dev --python "$PROJECT_PY" )
log project-venv "ok ($PROJECT_PY, uv=$UV)"

# ── 3. 模型权重（ModelScope） ─────────────────────────────────────────────
if [[ "$WANT_MODEL" == 1 ]]; then
  mkdir -p "$MODELS_DIR"
  if [[ -f "$MODEL_DIR/config.json" ]]; then
    log model "present: $MODEL_DIR"
  else
    log model "downloading $MODEL_ID → $MODEL_DIR"
    "$SV_PY" -m modelscope.cli.cli download --model "$MODEL_ID" --local_dir "$MODEL_DIR" 2>/dev/null \
      || "$SERVE_VENV/bin/modelscope" download --model "$MODEL_ID" --local_dir "$MODEL_DIR"
  fi
  sha256sum "$MODEL_DIR/config.json" | awk '{print $1}' > "$MODEL_DIR/.config.sha256"
fi

mkdir -p "$FINGERPRINT_DIR"
log done "serve venv: $SERVE_VENV · model: $MODEL_DIR"
