#!/usr/bin/env bash
# 录一条 trajectory：给目标仓库开一个独立 git worktree（不碰你的工作树），
# 用固定的 extension + 模型 + thinking 组合启动 pi。一批录制只改任务，不改这些。
#
#   bash scripts/record.sh <repo-path> <case-name>          # 开 worktree 并启动 pi
#   bash scripts/record.sh <repo-path> <case-name> --clean  # 录完后删掉 worktree
#
# worktree 放在 $AWL_REC_DIR（默认 ~/awl-rec）/<repo>-<case>，从当前 HEAD 分离检出。
# 录制模型可用 AWL_RECORD_MODEL 覆盖，但同一批必须一致（docs/decisions.md）。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

REPO="$(cd "${1:?usage: record.sh <repo-path> <case-name> [--clean]}" && pwd)"
CASE="${2:?usage: record.sh <repo-path> <case-name> [--clean]}"
MODEL="${AWL_RECORD_MODEL:-zai/glm-5.2:off}"
REC_DIR="${AWL_REC_DIR:-$HOME/awl-rec}"
WT="$REC_DIR/$(basename "$REPO")-$CASE"

if [[ "${3:-}" == "--clean" ]]; then
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"
  git -C "$REPO" worktree prune
  echo "removed $WT" >&2
  exit 0
fi

git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null
if [[ ! -d "$WT" ]]; then
  mkdir -p "$REC_DIR"
  git -C "$REPO" worktree add --detach "$WT" HEAD >&2
fi

# 录制前的自检：extension 在、模型可用、窗口已覆盖
[[ -f "$ROOT/extension/src/index.ts" ]] || { echo "extension missing" >&2; exit 1; }
PROVIDER="${MODEL%%/*}"; ID="${MODEL#*/}"; ID="${ID%%:*}"   # provider/id[:thinking]
LINE="$(pi --list-models 2>/dev/null | grep -E "^$PROVIDER +$ID " || true)"
[[ -n "$LINE" ]] || { echo "model not available: $MODEL" >&2; exit 1; }
grep -qE ' 65\.5K ' <<<"$LINE" || { echo "contextWindow override missing (want 65.5K): $LINE" >&2; exit 1; }

echo "worktree: $WT" >&2
echo "model:    $MODEL" >&2
echo "traces:   $ROOT/traces" >&2
cd "$WT"
exec pi -e "$ROOT/extension/src/index.ts" --trace-dir "$ROOT/traces" --model "$MODEL" --name "$(basename "$REPO")-$CASE"
