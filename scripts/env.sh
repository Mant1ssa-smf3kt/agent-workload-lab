#!/usr/bin/env bash
# 版本与路径的唯一来源。其余脚本 source 这个文件。
# 改任何一项都等于换实验环境：必须在 docs/decisions.md 记录，已有基线作废（CLAUDE.md §8.3）。

# ── 版本锁 ────────────────────────────────────────────────────────────────
export SGLANG_VERSION="${SGLANG_VERSION:-0.5.20}"        # PyPI，2026-09-18 时为最新
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

# ── 国内网络 ─────────────────────────────────────────────────────────────
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-$REMOTE_ROOT/modelscope-cache}"
