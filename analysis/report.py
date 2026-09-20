"""Report fragments from replay artifacts (``just report EXP``).

Two jobs, both enforcing CLAUDE.md §9:

1. **Variance** — all non-dry runs under ``experiments/<exp>/out/`` are one group. The report
   shows each run's key numbers and the spread across runs. Fewer than 3 runs, or runs whose
   fingerprints disagree (GPU / sglang / model / replayer commit), and the verdict says so.
2. **Compare** — ``--against OTHER`` puts two experiments side by side: EXP is the treatment,
   OTHER the control, so Δ = EXP − OTHER and the percentage is relative to OTHER. Refused when
   their fingerprints differ (§8.3) and flagged when their configs differ in more than one key.

    uv run python -m analysis.report baseline-c1
    uv run python -m analysis.report baseline-c1 --against baseline-c4
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.log import configure, get_logger

log = get_logger("analysis.report")
REPO_ROOT = Path(__file__).resolve().parents[1]

# Fields that make two runs "the same environment". Differ → not one table.
FINGERPRINT_KEYS = ("gpu", "sglang_version", "model", "pi_versions", "extension_versions")

# Config keys allowed to differ between compared experiments without a warning.
CONFIG_IGNORE = {"name", "notes", "out"}


@dataclass
class Run:
    exp: str
    run_id: str
    dir: Path
    summary: dict[str, Any]
    fingerprint: dict[str, Any]
    config: dict[str, Any]

    @property
    def replayer_commit(self) -> str | None:
        commit = (self.fingerprint.get("replayer") or {}).get("commit")
        return commit if isinstance(commit, str) else None

    def env_key(self) -> dict[str, Any]:
        return {k: self.fingerprint.get(k) for k in FINGERPRINT_KEYS} | {
            "replayer_commit": self.replayer_commit
        }


def load_runs(exp_dir: Path) -> list[Run]:
    out = exp_dir / "out"
    runs: list[Run] = []
    if not out.exists():
        return runs
    for d in sorted(out.iterdir()):
        if not d.is_dir() or d.name.endswith("-dry"):
            continue
        s, f = d / "summary.json", d / "fingerprint.json"
        if not (s.exists() and f.exists()):
            log.warning("incomplete run skipped", run=str(d))
            continue
        cfg_path = d / "config.resolved.yaml"
        config: dict[str, Any] = {}
        if cfg_path.exists():
            import yaml

            config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        runs.append(
            Run(
                exp=exp_dir.name,
                run_id=d.name,
                dir=d,
                summary=json.loads(s.read_text(encoding="utf-8")),
                fingerprint=json.loads(f.read_text(encoding="utf-8")),
                config=config,
            )
        )
    return runs


# ── key numbers ───────────────────────────────────────────────────────────

KEY_NUMBERS: tuple[tuple[str, tuple[str, ...], str, int], ...] = (
    # label, path into summary, unit, digits
    ("cache hit rate", ("all", "cache_hit_rate"), "", 4),
    ("cache hit rate (excl. synthetic)", ("excluding_synthetic", "cache_hit_rate"), "", 4),
    ("TTFT P50", ("all", "ttft_ms", "p50"), " ms", 0),
    ("TTFT P95", ("all", "ttft_ms", "p95"), " ms", 0),
    ("TTFT P99", ("all", "ttft_ms", "p99"), " ms", 0),
    ("latency P50", ("all", "latency_ms", "p50"), " ms", 0),
    ("latency P95", ("all", "latency_ms", "p95"), " ms", 0),
    ("latency P99", ("all", "latency_ms", "p99"), " ms", 0),
    ("prompt tokens total", ("all", "prompt_tokens_total"), "", 0),
    ("requests", ("all", "n"), "", 0),
    ("errors", ("n_errors",), "", 0),
    ("wall", ("wall_s",), " s", 1),
)


def dig(d: dict[str, Any], path: tuple[str, ...]) -> float | None:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return float(cur) if isinstance(cur, int | float) else None


def fmt(v: float | None, unit: str, digits: int) -> str:
    return "—" if v is None else f"{v:.{digits}f}{unit}"


# std 低于均值的这个比例视为零噪声（同配置重跑得到逐字节相同的结果时只剩浮点累加误差）
NOISE_FLOOR = 1e-9


@dataclass
class Spread:
    n: int
    mean: float | None
    std: float | None
    lo: float | None
    hi: float | None

    @property
    def cv(self) -> float | None:
        if self.mean is None or self.std is None or self.mean == 0:
            return None
        return self.std / abs(self.mean)


def spread(values: list[float | None]) -> Spread:
    xs = [v for v in values if v is not None]
    if not xs:
        return Spread(0, None, None, None, None)
    mean = sum(xs) / len(xs)
    std = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0
    return Spread(len(xs), mean, std, min(xs), max(xs))


# ── checks ────────────────────────────────────────────────────────────────


def env_consistent(runs: list[Run]) -> tuple[bool, list[str]]:
    if not runs:
        return True, []
    base = runs[0].env_key()
    problems: list[str] = []
    for r in runs[1:]:
        for k, v in r.env_key().items():
            if v != base.get(k):
                got, want = json.dumps(v, ensure_ascii=False), json.dumps(base.get(k), ensure_ascii=False)
                problems.append(f"{r.run_id}: {k} = {got} ≠ {want}")
    return not problems, problems


# Config subtrees that count as ONE variable when comparing experiments (name + params together).
ATOMIC_KEYS = {"transform"}


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and key not in ATOMIC_KEYS:
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def config_diff(a: dict[str, Any], b: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    fa, fb = _flatten(a), _flatten(b)
    diffs: list[tuple[str, Any, Any]] = []
    for k in sorted(set(fa) | set(fb)):
        if k.split(".")[0] in CONFIG_IGNORE:
            continue
        if fa.get(k) != fb.get(k):
            diffs.append((k, fa.get(k), fb.get(k)))
    return diffs


# ── rendering ─────────────────────────────────────────────────────────────


def render_variance(exp: str, runs: list[Run]) -> str:
    L: list[str] = [f"# {exp} · 方差", ""]
    if not runs:
        L.append("没有完成的 run（`out/` 下只有 dry-run 或空）。")
        return "\n".join(L) + "\n"
    ok, problems = env_consistent(runs)
    r0 = runs[0]
    fp = r0.fingerprint
    gpu = (fp.get("gpu") or {}).get("name") if isinstance(fp.get("gpu"), dict) else None
    model = (fp.get("model") or {}).get("id") if isinstance(fp.get("model"), dict) else None
    L.append(
        f"环境：GPU {gpu or 'TBD'} · sglang {fp.get('sglang_version') or 'TBD'} · model {model or 'TBD'} · "
        f"pi {', '.join(fp.get('pi_versions') or []) or 'TBD'} · replayer {(r0.replayer_commit or 'TBD')[:8]}"
    )
    cfg = r0.config.get("replay", {})
    L.append(
        f"配置：timing={cfg.get('timing')} · concurrency={cfg.get('concurrency')} · "
        f"transform={r0.config.get('transform', {}).get('name')} · traces={len(fp.get('traces') or [])}"
    )
    L.append("")
    if not ok:
        L.append("> **指纹不一致，以下数字不得放进同一张表（CLAUDE.md §8.3）：**")
        L.extend(f"> - {p}" for p in problems)
        L.append("")

    header = "| 指标 | " + " | ".join(r.run_id for r in runs) + " | mean ± std | min – max | CV |"
    L.append(header)
    L.append("|---|" + "---|" * len(runs) + "---|---|---|")
    for label, path, unit, digits in KEY_NUMBERS:
        vals = [dig(r.summary, path) for r in runs]
        sp = spread(vals)
        cells = " | ".join(fmt(v, unit, digits) for v in vals)
        ms = "—" if sp.mean is None else f"{fmt(sp.mean, unit, digits)} ± {fmt(sp.std, unit, digits)}"
        rng = "—" if sp.lo is None else f"{fmt(sp.lo, unit, digits)} – {fmt(sp.hi, unit, digits)}"
        cv = "—" if sp.cv is None else f"{sp.cv * 100:.1f}%"
        L.append(f"| {label} | {cells} | {ms} | {rng} | {cv} |")
    L.append("")

    verdict: list[str] = []
    if len(runs) < 3:
        verdict.append(f"只有 {len(runs)} 次 run，方差未确认（需要 ≥ 3 次同配置重跑）。")
    if not ok:
        verdict.append("指纹不一致，本组无效。")
    errs = sum(int(dig(r.summary, ("n_errors",)) or 0) for r in runs)
    if errs:
        verdict.append(f"共 {errs} 个请求出错，先查 requests.jsonl 里的 res_error。")
    L.append(
        "**判定**："
        + (" ".join(verdict) if verdict else "3 次以上同配置重跑，指纹一致，无错误；可用于对照。")
    )
    L.append("")
    return "\n".join(L)


def render_compare(a_name: str, a: list[Run], b_name: str, b: list[Run]) -> str:
    L: list[str] = [f"# {a_name} vs {b_name}", ""]
    if not a or not b:
        L.append("其中一方没有完成的 run。")
        return "\n".join(L) + "\n"
    ok, problems = env_consistent([*a, *b])
    if not ok:
        L.append("> **两组指纹不一致，不得对照（CLAUDE.md §8.3）：**")
        L.extend(f"> - {p}" for p in problems)
        L.append("")
    diffs = config_diff(a[0].config, b[0].config)
    L.append("配置差异：")
    if not diffs:
        L.append("- （无）— 这是同配置重跑，不是对照")
    for k, va, vb in diffs:
        L.append(f"- `{k}`: {json.dumps(va, ensure_ascii=False)} → {json.dumps(vb, ensure_ascii=False)}")
    if len(diffs) > 1:
        L.append("")
        L.append(f"> **动了 {len(diffs)} 个变量，违反一次只动一个（CLAUDE.md §9）；结论无效。**")
    L.append("")
    L.append(f"| 指标 | {a_name} (n={len(a)}) | {b_name} (n={len(b)}) | Δ (A − B) | Δ / 噪声 |")
    L.append("|---|---|---|---|---|")
    for label, path, unit, digits in KEY_NUMBERS:
        sa = spread([dig(r.summary, path) for r in a])
        sb = spread([dig(r.summary, path) for r in b])
        if sa.mean is None or sb.mean is None:
            L.append(f"| {label} | {fmt(sa.mean, unit, digits)} | {fmt(sb.mean, unit, digits)} | — | — |")
            continue
        # A 是实验组、B 是对照组：Δ 为正即实验组数值更高，百分比以对照组为分母
        delta = sa.mean - sb.mean
        rel = f" ({delta / sb.mean * 100:+.1f}%)" if sb.mean else ""
        noise = max(sa.std or 0.0, sb.std or 0.0)
        # 三次重跑逐字节相同时 std 只剩浮点误差（~1e-17），按零噪声处理，否则打出 1e15×
        if noise <= NOISE_FLOOR * max(abs(sa.mean), abs(sb.mean)):
            ratio = "∞（零噪声）" if delta else "—"
        else:
            ratio = f"{abs(delta) / noise:.1f}×"
        ca = f"{fmt(sa.mean, unit, digits)} ± {fmt(sa.std, unit, digits)}"
        cb = f"{fmt(sb.mean, unit, digits)} ± {fmt(sb.std, unit, digits)}"
        L.append(f"| {label} | {ca} | {cb} | {fmt(delta, unit, digits)}{rel} | {ratio} |")
    L.append("")
    L.append(
        f"Δ = {a_name} − {b_name}（实验组 − 对照组），百分比相对对照组。"
        "Δ / 噪声 = |Δ| / max(std_A, std_B)。小于 ~2× 时效应与噪声同量级，结论作废（CLAUDE.md §9）。"
    )
    notes: list[str] = []
    if len(a) < 3 or len(b) < 3:
        notes.append("至少一方不足 3 次重跑，方差未确认。")
    if not ok:
        notes.append("指纹不一致。")
    if len(diffs) > 1:
        notes.append("多于一个变量。")
    L.append("**判定**：" + (" ".join(notes) if notes else "可下结论。"))
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp", help="experiment name under experiments/")
    ap.add_argument("--against", help="second experiment to compare with")
    ap.add_argument("--experiments-dir", type=Path, default=REPO_ROOT / "experiments")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing report.md")
    args = ap.parse_args(argv)
    configure()

    a_dir = args.experiments_dir / args.exp
    if not a_dir.exists():
        log.error("experiment not found", dir=str(a_dir))
        return 2
    a = load_runs(a_dir)
    if args.against:
        b_dir = args.experiments_dir / args.against
        if not b_dir.exists():
            log.error("experiment not found", dir=str(b_dir))
            return 2
        text = render_compare(args.exp, a, args.against, load_runs(b_dir))
        target = a_dir / f"compare-{args.against}.md"
    else:
        text = render_variance(args.exp, a)
        target = a_dir / "report.md"
    if args.stdout:
        sys.stdout.write(text)
    else:
        target.write_text(text, encoding="utf-8")
        log.info("wrote report", path=str(target), runs=len(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
