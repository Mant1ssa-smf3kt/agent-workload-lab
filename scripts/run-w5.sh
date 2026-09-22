#!/usr/bin/env bash
# 远端：W5 全部批次自动串行运行，跑完关机（CLAUDE.md §11；开卡与自动运行由人于 2026-09-22 确认）。
# 写成文件再 nohup，别把命令文本塞进 bash -c（pgrep 会匹配到自己）。
#
#   setsid nohup bash scripts/run-w5.sh > /root/autodl-tmp/w5-chain.log 2>&1 < /dev/null &
#
# 阶段（每批各 3 次，run-batch.sh 跑完自动出 report.md）：
#   1. 等已由人启动的批 1（run-batch.sh 3 w5-control w5-tail）结束
#   2. 同一 server session 跑批 2：w5-c4 w5-c4-tail w5-c4-truncate
#   3. 批 3 两组各自冷启动 server，使 --schedule-policy 成为唯一差异：
#        重启 server（lpm）→ w5-c8-lpm；重启 server（SCHEDULE_POLICY=fcfs）→ w5-c8-fcfs
#   4. 停 server，`shutdown`（AutoDL 的关机脚本：杀 supervisord，容器停止计费）。
#      out/ 与日志都在 /root/autodl-tmp（数据盘），关机不丢；之后无卡模式开机 `sync.sh --pull` 拉回。
#
# 任何阶段失败都继续到下一阶段并记日志；server 起不来则跳过该批。除非 NO_SHUTDOWN=1，结束一律关机。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" && source scripts/env.sh
export PATH="/root/miniconda3/bin:$PATH"
LOGDIR="$REMOTE_ROOT"
log() { printf '{"ts":"%s","chain":"%s","msg":"%s"}\n' "$(date -Is)" "$1" "$2"; }

serve_pid() { pgrep -f "python -m sglang.launch_server" | head -1; }
server_up() { curl -sf -m 5 "$SGLANG_HOST:$SGLANG_PORT/v1/models" >/dev/null; }

stop_server() {
  local pid; pid="$(serve_pid)"
  [[ -z "$pid" ]] && { log server "no server running"; return 0; }
  log server "stopping server pid $pid (pgid $(ps -o pgid= -p "$pid" | tr -d ' '))"
  kill -TERM -- "-$(ps -o pgid= -p "$pid" | tr -d ' ')" 2>/dev/null || kill -TERM "$pid"
  for _ in $(seq 1 60); do
    sleep 2
    pgrep -f "sglang::|sglang\.launch_server" >/dev/null || break
  done
  pgrep -f "sglang::|sglang\.launch_server" >/dev/null && { log server "SIGKILL leftovers"; pkill -9 -f "sglang::|sglang\.launch_server"; sleep 5; }
  local used; used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
  log server "server stopped; gpu mem used ${used} MiB"
}

# start_server <policy> <tag>：后台起 serve.sh，等 ready；失败返回 1
start_server() {
  local policy="$1" tag="$2" logf="$LOGDIR/serve-w5-$2.log"
  log server "starting server schedule-policy=$policy → $logf"
  SCHEDULE_POLICY="$policy" setsid nohup bash scripts/serve.sh > "$logf" 2>&1 < /dev/null &
  for _ in $(seq 1 90); do   # 最多 15 min（flashinfer JIT 已缓存，正常 < 2 min）
    sleep 10
    grep -q "ready to roll" "$logf" && server_up && { log server "server ready ($tag): $(readlink -f "$FINGERPRINT_DIR/serve-latest.json")"; return 0; }
    serve_pid >/dev/null || { log server "server process exited early ($tag); tail: $(tail -3 "$logf" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  done
  log server "server not ready after 15 min ($tag)"; return 1
}

run_batch() {  # run_batch <tag> <exp>...
  local tag="$1"; shift
  server_up || { log "$tag" "server down; skipping batch: $*"; return 1; }
  log "$tag" "batch start: $*"
  bash scripts/run-batch.sh 3 "$@" > "$LOGDIR/batch-w5-$tag.log" 2>&1
  log "$tag" "batch end (rc=$?); $(grep -c FAILED "$LOGDIR/batch-w5-$tag.log") failed runs"
}

T0=$(date +%s)
log chain "start; waiting for batch 1 (run-batch.sh) to finish"
while pgrep -f "scripts/run-batch.sh" >/dev/null; do sleep 60; done
log chain "batch 1 finished: $(tail -1 "$LOGDIR/batch-w5-1.log" 2>/dev/null | cut -c1-200)"

# 批 2：同一 session（与批 1 一样是 lpm 热缓存；c4/real 下驱逐主导，与 W4 做法一致）
run_batch 2 w5-c4 w5-c4-tail w5-c4-truncate

# 批 3：两组各自冷启动，只差 --schedule-policy
stop_server
if start_server lpm 3-lpm; then run_batch 3-lpm w5-c8-lpm; fi
stop_server
if start_server fcfs 3-fcfs; then run_batch 3-fcfs w5-c8-fcfs; fi
stop_server

log chain "all batches done in $(( ($(date +%s) - T0) / 60 )) min; runs per experiment:"
for exp in w5-control w5-tail w5-c4 w5-c4-tail w5-c4-truncate w5-c8-lpm w5-c8-fcfs; do
  n=$(ls -d "experiments/$exp/out/"*/summary.json 2>/dev/null | wc -l | tr -d ' ')
  log chain "  $exp: $n runs with summary.json"
done
sync
if [[ "${NO_SHUTDOWN:-0}" == "1" ]]; then log chain "NO_SHUTDOWN=1; leaving instance on"; exit 0; fi
log chain "shutting down instance"
shutdown
