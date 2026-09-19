#!/usr/bin/env bash
# 核对 docs/recording-tasks.md 里引用的仓库路径是否存在（录制前跑一次，避免让 agent 去找不存在的文件）。
set -uo pipefail
P=~/Projects
repo_dir() {  # macOS 自带 bash 3.2 没有关联数组
  case "$1" in
    minimind) echo "$P/minimind" ;; openclaw) echo "$P/Learn-OpenClaw" ;;
    rr) echo "$P/reactive-resume" ;; awl) echo "$P/ClawEval" ;;
  esac
}
check() { # repo relpath...
  local r; r="$(repo_dir "$1")"; shift
  for f in "$@"; do
    if compgen -G "$r/$f" >/dev/null; then echo "ok      $1  $f"; else echo "MISSING $1  $f"; fail=1; fi
  done
}
fail=0
check minimind model/model_minimind.py dataset/lm_dataset.py dataset/dataset.md trainer/trainer_utils.py trainer/train_pretrain.py trainer/train_full_sft.py trainer/train_lora.py trainer/train_dpo.py scripts/serve_openai_api.py scripts/chat_api.py README.md
check openclaw core/node.py core/memory.py examples/workflow/main.py examples/chatbot_with_memory tools/executor.py tools/mcp/server.py tools/mcp/client.py tools/mcp/example.py tools/builtins/grep.py tools/builtins/read.py tools/builtins/ls.py tools/builtins/find.py tools/builtins/write.py tools/builtins/edit.py tools/builtins/tool_def.py tests/test_memory.py
check rr packages/import/src/date.ts packages/import/src/date.test.ts packages/import/src/level.ts packages/import/src/html.ts packages/import/src/json-resume.tsx packages/import/src/reactive-resume-json.tsx packages/import/src/reactive-resume-v4-json.tsx packages/schema/src/resume/data.ts packages/schema/src/resume/sample.ts packages/schema/src/templates.ts packages/pdf/src/document.tsx packages/pdf/src/context.tsx packages/pdf/src/semantic/legacy-parity.ts "packages/pdf/src/ats-extraction*.tsx" "packages/resume/src/ats*" packages/docx/src apps/server/src/rpc apps/server/src/openapi apps/server/src/mcp packages/api packages/db "apps/web/src/features/resume"
check awl analysis/stats.py analysis/profile.py analysis/tests/test_profile.py replay/client.py replay/tests/test_client.py
# 函数/类名核对
grep -q "class MOEFeedForward" "$(repo_dir minimind)/model/model_minimind.py" && echo "ok      minimind  MOEFeedForward" || { echo "MISSING minimind MOEFeedForward"; fail=1; }
grep -q "def get_lr" "$(repo_dir minimind)/trainer/trainer_utils.py" && echo "ok      minimind  get_lr" || { echo "MISSING minimind get_lr"; fail=1; }
grep -q "def precompute_freqs_cis" "$(repo_dir minimind)/model/model_minimind.py" && echo "ok      minimind  precompute_freqs_cis" || { echo "MISSING minimind precompute_freqs_cis"; fail=1; }
grep -q "def demo" "$(repo_dir openclaw)/tools/executor.py" && echo "ok      openclaw  executor.demo" || { echo "MISSING openclaw executor.demo"; fail=1; }
grep -q "def compress" "$(repo_dir openclaw)/core/memory.py" && echo "ok      openclaw  Memory.compress" || { echo "MISSING openclaw Memory.compress"; fail=1; }
grep -q "def percentile" "$(repo_dir awl)/analysis/stats.py" && echo "ok      awl       percentile" || { echo "MISSING awl percentile"; fail=1; }
grep -q "aiter_lines" "$(repo_dir awl)/replay/client.py" && echo "ok      awl       aiter_lines" || { echo "MISSING awl aiter_lines"; fail=1; }
exit $fail
