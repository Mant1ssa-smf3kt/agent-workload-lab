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
#
# ONLY_BATCH3=1：跳过阶段 1、2，直接从批 3 开始（2026-09-22 批 3 因启动竞态未跑成，补跑用）：
#   ONLY_BATCH3=1 setsid nohup bash scripts/run-w5.sh > /root/autodl-tmp/w5-chain-batch3.log 2>&1 < /dev/null &
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" && source scripts/env.sh
export PATH="/root/miniconda3/bin:$PATH"
LOGDIR="$REMOTE_ROOT"
log() { printf '{"ts":"%s","chain":"%s","msg":"%s"}\n' "$(date -Is)" "$1" "$2"; }

# 本脚本起的 server 记 SERVE_PID（serve.sh 最后 exec python，pid 不变；setsid 使其自成进程组）。
# 不能用 pgrep 判活：serve.sh 在 exec 前先跑 fingerprint.sh（约 20 s），那段时间 pgrep 查不到 python，
# 2026-09-22 批 3 因此把正在加载的 lpm server 误判为退出，接着起的 fcfs 撞上它 OOM。
SERVE_PID=""
serve_pid() { pgrep -f "python -m sglang.launch_server" | head -1; }
any_server() { pgrep -f "sglang::|sglang\.launch_server|scripts/serve\.sh" >/dev/null; }
server_up() { curl -sf -m 5 "$SGLANG_HOST:$SGLANG_PORT/v1/models" >/dev/null; }

stop_server() {
  local pid="${SERVE_PID:-$(serve_pid)}"   # 批 1 的 server 是人起的，只能 pgrep 找
  SERVE_PID=""
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    log server "no tracked server running"
  else
    log server "stopping server pid $pid (pgid $(ps -o pgid= -p "$pid" | tr -d ' '))"
    kill -TERM -- "-$(ps -o pgid= -p "$pid" | tr -d ' ')" 2>/dev/null || kill -TERM "$pid"
  fi
  for _ in $(seq 1 60); do
    any_server || break
    sleep 2
  done
  any_server && { log server "SIGKILL leftovers"; pkill -9 -f "sglang::|sglang\.launch_server|scripts/serve\.sh"; sleep 5; }
  local used; used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
  log server "server stopped; gpu mem used ${used} MiB"
}

# start_server <policy> <tag>：后台起 serve.sh，等 ready；失败返回 1（并清掉自己起的进程）
start_server() {
  local policy="$1" tag="$2" logf="$LOGDIR/serve-w5-$2.log"
  any_server && { log server "refusing to start ($tag): another server process is still alive"; return 1; }
  log server "starting server schedule-policy=$policy → $logf"
  SCHEDULE_POLICY="$policy" setsid nohup bash scripts/serve.sh > "$logf" 2>&1 < /dev/null &
  SERVE_PID=$!
  for _ in $(seq 1 90); do   # 最多 15 min（flashinfer JIT 已缓存，正常 < 2 min）
    sleep 10
    grep -q "ready to roll" "$logf" && server_up && { log server "server ready ($tag, pid $SERVE_PID): $(readlink -f "$FINGERPRINT_DIR/serve-latest.json")"; return 0; }
    kill -0 "$SERVE_PID" 2>/dev/null || { log server "server process exited early ($tag); tail: $(tail -3 "$logf" | tr '\n' ' ' | cut -c1-300)"; SERVE_PID=""; return 1; }
  done
  log server "server not ready after 15 min ($tag)"; stop_server; return 1
}

run_batch() {  # run_batch <tag> <exp>...
  local tag="$1"; shift
  server_up || { log "$tag" "server down; skipping batch: $*"; return 1; }
  log "$tag" "batch start: $*"
  bash scripts/run-batch.sh 3 "$@" > "$LOGDIR/batch-w5-$tag.log" 2>&1
  log "$tag" "batch end (rc=$?); $(grep -c FAILED "$LOGDIR/batch-w5-$tag.log") failed runs"
}

T0=$(date +%s)
if [[ "${ONLY_BATCH3:-0}" == "1" ]]; then
  log chain "start; ONLY_BATCH3=1, skipping batches 1 and 2"
else
  log chain "start; waiting for batch 1 (run-batch.sh) to finish"
  while pgrep -f "scripts/run-batch.sh" >/dev/null; do sleep 60; done
  log chain "batch 1 finished: $(tail -1 "$LOGDIR/batch-w5-1.log" 2>/dev/null | cut -c1-200)"

  # 批 2：同一 session（与批 1 一样是 lpm 热缓存；c4/real 下驱逐主导，与 W4 做法一致）
  run_batch 2 w5-c4 w5-c4-tail w5-c4-truncate
fi

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
