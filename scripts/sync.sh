#!/usr/bin/env bash
# 本地 → 远端单向同步（rsync）。排除 traces/ 与 experiments/*/out/（CLAUDE.md §6）。
# 远端连接信息放 scripts/remote.env（不入库），格式见 remote.env.example。
#
#   bash scripts/sync.sh            # 同步代码
#   bash scripts/sync.sh --traces   # 额外同步 traces/（重放前需要；单向，远端不会改它）
#   bash scripts/sync.sh --pull EXP # 反向：拉回 experiments/EXP/out/ 到本地
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# shellcheck source=env.sh
source "$HERE/env.sh"
[[ -f "$HERE/remote.env" ]] || { echo "missing scripts/remote.env (copy remote.env.example)" >&2; exit 1; }
# shellcheck source=remote.env.example
source "$HERE/remote.env"
: "${REMOTE_HOST:?}" "${REMOTE_PORT:?}" "${REMOTE_USER:=root}"

SSH="ssh -p $REMOTE_PORT"
DEST="$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
# macOS 自带 rsync 2.6.9 没有 --info；rsync ≥ 3.1 才有整体进度条
if rsync --info=progress2 --version >/dev/null 2>&1; then PROGRESS="--info=progress2"; else PROGRESS="--progress"; fi
RSYNC=(rsync -az "$PROGRESS" -e "$SSH")
EXCLUDES=(
  --exclude '.git/' --exclude 'node_modules/' --exclude '.venv/' --exclude '__pycache__/'
  --exclude '.mypy_cache/' --exclude '.ruff_cache/' --exclude '.pytest_cache/'
  --exclude 'traces/' --exclude 'experiments/*/out/' --exclude 'scripts/remote.env' --exclude '.DS_Store'
)

# 远端没有 .git（被排除）；把本地 HEAD 与 dirty 状态写成 .sync-commit 一起同步，供指纹读取（CLAUDE.md §9）
{
  echo "commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "dirty=$(git -C "$ROOT" status --porcelain --untracked-files=no 2>/dev/null | grep -q . && echo true || echo false)"
  echo "synced_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$ROOT/.sync-commit"

case "${1:-}" in
  --pull)
    EXP="${2:?usage: sync.sh --pull EXP}"
    mkdir -p "$ROOT/experiments/$EXP/out"
    "${RSYNC[@]}" "$DEST/experiments/$EXP/out/" "$ROOT/experiments/$EXP/out/"
    ;;
  --traces)
    "${RSYNC[@]}" "${EXCLUDES[@]}" "$ROOT/" "$DEST/"
    "${RSYNC[@]}" "$ROOT/traces/" "$DEST/traces/"
    ;;
  "")
    $SSH "$REMOTE_USER@$REMOTE_HOST" "mkdir -p '$REMOTE_DIR'"
    "${RSYNC[@]}" "${EXCLUDES[@]}" "$ROOT/" "$DEST/"
    ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac
