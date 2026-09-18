# 常用命令（CLAUDE.md §7）。需要 `just`：brew install just
# 所有本地目标不需要 GPU；标「需要开卡」的目标不得由 agent 自动执行。

set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

# 单元测试：Python + extension
test: test-py test-ext

test-py:
    uv run pytest

test-ext:
    cd extension && npm test

# 格式与类型检查
lint: lint-py lint-ext

lint-py:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy

lint-ext:
    cd extension && npm run typecheck

fmt:
    uv run ruff format .
    uv run ruff check --fix .

# extension 端到端冒烟：真 pi + 假 OpenAI 服务器，零凭证零花费
smoke-ext:
    cd extension && npm run smoke

# W1 负载画像表：从 traces/ 读 trace，输出到 OUT（默认 experiments/profile/out）
profile TRACES="traces" OUT="experiments/profile/out":
    uv run python -m analysis.profile "{{TRACES}}" --out "{{OUT}}"

# 从 experiments/EXP/out/ 生成报告片段（W2+）
report EXP:
    @echo "TBD: analysis.report not implemented yet (W2)"; exit 1

# 远端·无卡：不连推理服务，只验证 trajectory 解析与调度逻辑（W2）
replay-dry EXP:
    @echo "TBD: replay not implemented yet (W2)"; exit 1

# 远端·需要开卡：正式重放，落盘 artifact（W2）。agent 不得自动执行。
replay EXP:
    @echo "TBD: replay not implemented yet (W2)"; exit 1
