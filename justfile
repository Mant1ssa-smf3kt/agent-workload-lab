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

# 从 experiments/EXP/out/ 下所有完成的 run 生成方差报告 → experiments/EXP/report.md
report EXP:
    uv run python -m analysis.report "{{EXP}}"

# 两个实验对照（校验指纹一致、只动一个变量）→ experiments/EXP/compare-OTHER.md
compare EXP OTHER:
    uv run python -m analysis.report "{{EXP}}" --against "{{OTHER}}"

# summary 口径变了（docs/decisions.md）时，从 requests.jsonl 重算已完成 run 的 summary.json（旧的留作 summary.prev.json）
resummarize +EXPS:
    uv run python -m replay.resummarize {{EXPS}}

# 从 experiments/*/out/ 出图（W4 并发扫描、W3 上下文改写）→ docs/figures/*.png + 同名 .csv
plot OUT="docs/figures":
    uv run python -m analysis.plot --out "{{OUT}}"

# 无卡即可：不连推理服务，只构建计划（payload 归一化、间隔、合成 compaction）→ experiments/EXP/out/<ts>-dry/
replay-dry EXP:
    uv run python -m replay.run "experiments/{{EXP}}/config.yaml" --dry-run

# 【需要开卡，按小时计费。agent 不得自动执行，必须先向人确认。】正式重放 → experiments/EXP/out/<ts>/
replay EXP:
    uv run python -m replay.run "experiments/{{EXP}}/config.yaml"

# 【需要开卡】远端：串行跑一批实验各 N 次并出报告（后台运行，日志 /root/autodl-tmp/batch.log）
batch REPEATS +EXPS:
    nohup bash scripts/run-batch.sh {{REPEATS}} {{EXPS}} > /root/autodl-tmp/batch.log 2>&1 &
