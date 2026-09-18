#!/usr/bin/env bash
# 版本与路径的唯一来源。其余脚本 source 这个文件。
# 改任何一项都等于换实验环境：必须在 docs/decisions.md 记录，已有基线作废（CLAUDE.md §8.3）。

# ── 版本锁 ────────────────────────────────────────────────────────────────
# sglang ≥ 0.5.12 是 CUDA 13 栈（torch 2.11/2.13 cu13 + flashinfer[cu13]），宿主机驱动必须 ≥ 580；
# 4090/5090 是消费卡，没有 forward-compat。驱动只到 CUDA 12.x 的机器用 0.5.10（torch 2.9.1 cu128，最后一个 cu12 版）。
export SGLANG_VERSION="${SGLANG_VERSION:-0.5.20}"        # PyPI，2026-09-18 时为最新
export SGLANG_MIN_DRIVER="${SGLANG_MIN_DRIVER:-580}"      # 与上面的版本配套；换 0.5.10 时改成 525
export MODELSCOPE_VERSION="${MODELSCOPE_VERSION:-1.40.1}"

# ── 重放模型 ─────────────────────────────────────────────────────────────
# 单卡 4090 (24GB) / 5090 (32GB)。FP8 权重 ~8GB，给 KV cache 留出 ≥14GB，
# 才装得下多条并发的长 agent 上下文；bf16 8B 只剩 ~6GB KV，不够做缓存实验。
export MODEL_ID="${MODEL_ID:-Qwen/Qwen3-8B-FP8}"          # ModelScope id
export MODEL_QUANT="${MODEL_QUANT:-fp8}"                  # 写进指纹，人读
export TOOL_CALL_PARSER="${TOOL_CALL_PARSER:-qwen25}"
export REASONING_PARSER="${REASONING_PARSER:-qwen3}"

# ── 远端路径（AutoDL：/root/autodl-tmp 是数据盘，重启不丢） ───────────────
export REMOTE_ROOT="${REMOTE_ROOT:-/root/autodl-tmp}"
export REMOTE_DIR="${REMOTE_DIR:-$REMOTE_ROOT/agent-workload-lab}"
export MODELS_DIR="${MODELS_DIR:-$REMOTE_ROOT/models}"
export MODEL_DIR="${MODEL_DIR:-$MODELS_DIR/$MODEL_ID}"
export SERVE_VENV="${SERVE_VENV:-$REMOTE_ROOT/venv-serve}"  # SGLang 单独一个 venv，与项目 venv 隔离
export FINGERPRINT_DIR="${FINGERPRINT_DIR:-$REMOTE_ROOT/fingerprints}"

# ── 服务 ─────────────────────────────────────────────────────────────────
export SGLANG_HOST="${SGLANG_HOST:-127.0.0.1}"
export SGLANG_PORT="${SGLANG_PORT:-30000}"

# ── 国内网络 / 磁盘 ──────────────────────────────────────────────────────
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-$REMOTE_ROOT/modelscope-cache}"
# AutoDL 系统盘只有 30GB；pip 缓存 + 解包临时目录（sglang 全家桶 >6GB）放数据盘
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$REMOTE_ROOT/pip-cache}"
export TMPDIR="${TMPDIR:-$REMOTE_ROOT/tmp}"
mkdir -p "$PIP_CACHE_DIR" "$TMPDIR" 2>/dev/null || true
