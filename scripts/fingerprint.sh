#!/usr/bin/env bash
# 环境指纹（CLAUDE.md §9）。输出一个 JSON 到 stdout。
# serve.sh 在起服务时调用并落盘；replayer 读它写进 artifact。缺任何一项的 artifact 视为无效
# ——所以缺的项这里写 null，让下游能识别，而不是静默略过。
#
#   bash scripts/fingerprint.sh [serve-args...]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
source "$HERE/env.sh"

PY="$SERVE_VENV/bin/python"
[[ -x "$PY" ]] || PY=python3

# ── 收集（全部进环境变量，Python 侧只读，不做 shell 模板） ────────────────
if command -v nvidia-smi >/dev/null 2>&1; then
  FP_GPU_CSV="$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 || true)"
else
  FP_GPU_CSV=""
fi
FP_CUDA="$("$PY" -c 'import torch; print(torch.version.cuda or "")' 2>/dev/null || true)"
FP_SGLANG="$("$PY" -c 'import sglang; print(sglang.__version__)' 2>/dev/null || true)"
FP_TORCH="$("$PY" -c 'import torch; print(torch.__version__)' 2>/dev/null || true)"
FP_PYTHON="$("$PY" -c 'import sys; print(sys.version.split()[0])')"
FP_MODEL_SHA="$(cat "$MODEL_DIR/.config.sha256" 2>/dev/null || (sha256sum "$MODEL_DIR/config.json" 2>/dev/null | awk '{print $1}') || true)"
FP_COMMIT="$(git -C "$HERE/.." rev-parse HEAD 2>/dev/null || true)"
FP_DIRTY="$(if git -C "$HERE/.." status --porcelain 2>/dev/null | grep -q .; then echo 1; else echo 0; fi)"
export FP_GPU_CSV FP_CUDA FP_SGLANG FP_TORCH FP_PYTHON FP_MODEL_SHA FP_COMMIT FP_DIRTY
export MODEL_ID MODEL_DIR MODEL_QUANT

"$PY" - "$@" <<'PYEOF'
import json, os, socket, sys, time

def nz(s):
    return s if s else None

gpu = None
csv = os.environ.get("FP_GPU_CSV", "")
if csv:
    parts = [p.strip() for p in csv.split(",")]
    if len(parts) >= 3:
        gpu = {"name": parts[0], "driver": parts[1], "memory_mib": int(parts[2]) if parts[2].isdigit() else None}

print(json.dumps({
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "hostname": socket.gethostname(),
    "gpu": gpu,
    "cuda": nz(os.environ.get("FP_CUDA")),
    "sglang_version": nz(os.environ.get("FP_SGLANG")),
    "torch_version": nz(os.environ.get("FP_TORCH")),
    "python": os.environ["FP_PYTHON"],
    "model": {
        "id": os.environ["MODEL_ID"],
        "dir": os.environ["MODEL_DIR"],
        "quant": os.environ["MODEL_QUANT"],
        "config_sha256": nz(os.environ.get("FP_MODEL_SHA")),
    },
    "serve_args": sys.argv[1:],
    "repo_commit": nz(os.environ.get("FP_COMMIT")),
    "repo_dirty": os.environ.get("FP_DIRTY") == "1",
}, ensure_ascii=False, indent=2))
PYEOF
