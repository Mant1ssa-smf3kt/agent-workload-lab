"""Figures from replay artifacts (``just plot``).

Three figures, each in a light and a dark variant plus a CSV twin holding exactly the plotted
numbers (CLAUDE.md §8.4: every number traces to ``experiments/*/out/*/summary.json``):

- ``w4-concurrency``: cache hit rate, evicted tokens, TTFT P95 and turn-latency P95 against
  concurrency for the append-only replays, with the system_timestamp replay at c=4 as a marker.
- ``w3-transforms``: the same three latency/cache numbers for the four W3 context transforms.
- ``w5-followups``: cache hit rate plus TTFT and turn-latency P50 / P95 / P99 / max per W5 group
  (timestamp moved to the end of the messages, truncation under load, FCFS vs LPM at c=8), each
  beside its own re-run control. Values right-censored by the client timeout are drawn hollow.

Marks over three repeats show the mean with a min–max range bar. Groups with no finished
runs are skipped with a warning rather than failing the whole render.

    uv run python -m analysis.plot --out docs/figures
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from analysis.log import configure, get_logger
from analysis.report import Run, censored, dig, load_runs

log = get_logger("analysis.plot")
REPO_ROOT = Path(__file__).resolve().parents[1]

W4_SWEEP = ("w4-c1", "w4-c2", "w4-c4", "w4-c8")
W4_TIMESTAMP = "w4-c4-timestamp"
W3_GROUPS = (
    ("w3-control", "append-only (control)"),
    ("w3-timestamp", "system_timestamp"),
    ("w3-tools-rotate", "tools_rotate"),
    ("w3-truncate", "truncate_tool_results"),
)
# (concurrency label, ((experiment, row label, series), ...)); each block holds its own control.
W5_BLOCKS = (
    (
        "c=1",
        (
            ("w5-control", "append-only", "append-only (control)"),
            ("w5-tail", "timestamp at end of messages", "timestamp at end of messages"),
        ),
    ),
    (
        "c=4",
        (
            ("w5-c4", "append-only", "append-only (control)"),
            ("w5-c4-tail", "timestamp at end of messages", "timestamp at end of messages"),
            ("w5-c4-truncate", "truncate_tool_results", "truncate_tool_results"),
        ),
    ),
    (
        "c=8",
        (
            ("w5-c8-lpm", "append-only · LPM", "append-only (control)"),
            ("w5-c8-fcfs", "append-only · FCFS", "FCFS scheduling"),
        ),
    ),
)
W5_MARKS = (("p50", "o", "P50"), ("p95", "D", "P95"), ("p99", "s", "P99"), ("max", "^", "max"))

# Series colors follow the entity across both figures (dataviz palette, slots 1–4).
THEMES: dict[str, dict[str, Any]] = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series": {
            "append-only (control)": "#2a78d6",
            "system_timestamp": "#eb6834",
            "tools_rotate": "#1baf7a",
            "truncate_tool_results": "#eda100",
            "timestamp at end of messages": "#e87ba4",
            "FCFS scheduling": "#008300",
        },
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series": {
            "append-only (control)": "#3987e5",
            "system_timestamp": "#d95926",
            "tools_rotate": "#199e70",
            "truncate_tool_results": "#c98500",
            "timestamp at end of messages": "#d55181",
            "FCFS scheduling": "#008300",
        },
    },
}


@dataclass
class Stat:
    mean: float
    lo: float
    hi: float
    n: int


def _stat(values: list[float | None]) -> Stat | None:
    xs = [v for v in values if v is not None]
    if not xs:
        return None
    return Stat(sum(xs) / len(xs), min(xs), max(xs), len(xs))


def evicted_tokens(run: Run) -> float | None:
    after = dig(run.summary, ("metrics_after", "sglang:evicted_tokens_total"))
    before = dig(run.summary, ("metrics_before", "sglang:evicted_tokens_total"))
    if after is None or before is None:
        return None
    return after - before


METRICS: tuple[tuple[str, str, Any], ...] = (
    # key, axis label, extractor
    ("cache_hit_rate", "Cache hit rate", lambda r: dig(r.summary, ("all", "cache_hit_rate"))),
    ("evicted_mtok", "Evicted tokens per run (M)", lambda r: _mtok(evicted_tokens(r))),
    ("ttft_p95_s", "TTFT P95 (s)", lambda r: _sec(dig(r.summary, ("all", "ttft_ms", "p95")))),
    ("latency_p95_s", "Turn latency P95 (s)", lambda r: _sec(dig(r.summary, ("all", "latency_ms", "p95")))),
)


def _sec(ms: float | None) -> float | None:
    return None if ms is None else ms / 1000.0


def _mtok(tok: float | None) -> float | None:
    return None if tok is None else tok / 1e6


def group_stats(runs: list[Run]) -> dict[str, Stat | None]:
    return {key: _stat([fn(r) for r in runs]) for key, _, fn in METRICS}


# ── styling ───────────────────────────────────────────────────────────────


def _style(ax: Axes, t: dict[str, Any], *, ygrid: bool) -> None:
    ax.set_facecolor(t["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(t["axis"])
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(colors=t["muted"], labelcolor=t["ink2"], labelsize=8, length=0)
    ax.grid(axis="y" if ygrid else "x", color=t["grid"], linewidth=1.0, linestyle="-")
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(t["ink2"])
    ax.yaxis.label.set_color(t["ink2"])


def _fig(ncols: int, t: dict[str, Any], width: float, height: float) -> Any:
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), facecolor=t["surface"])
    return fig, list(axes)


# ── figure 1: concurrency sweep ───────────────────────────────────────────


def render_concurrency(exp_dir: Path, out: Path, theme: str) -> list[Path]:
    t = THEMES[theme]
    sweep: list[tuple[int, dict[str, Stat | None]]] = []
    for name in W4_SWEEP:
        runs = load_runs(exp_dir / name)
        if not runs:
            log.warning("no finished runs, skipped", exp=name)
            continue
        sweep.append((int(runs[0].config.get("replay", {}).get("concurrency", 0)), group_stats(runs)))
    ts_runs = load_runs(exp_dir / W4_TIMESTAMP)
    ts: tuple[int, dict[str, Stat | None]] | None = None
    if ts_runs:
        ts = (int(ts_runs[0].config.get("replay", {}).get("concurrency", 0)), group_stats(ts_runs))
    else:
        log.warning("no finished runs, skipped", exp=W4_TIMESTAMP)
    if not sweep:
        return []

    ctrl_label, ts_label = "append-only (control)", "system_timestamp"
    fig, axes = _fig(len(METRICS), t, 12.0, 3.2)
    xs = [c for c, _ in sweep]
    for ax, (key, label, _) in zip(axes, METRICS, strict=True):
        _style(ax, t, ygrid=True)
        pts = [(c, s[key]) for c, s in sweep if s[key] is not None]
        if pts:
            ys = [st.mean for _, st in pts if st]
            ax.plot(
                [c for c, _ in pts],
                ys,
                color=t["series"][ctrl_label],
                linewidth=2,
                marker="o",
                markersize=8,
                markeredgecolor=t["surface"],
                markeredgewidth=2,
                label=ctrl_label,
                zorder=3,
            )
            for c, st in pts:
                if st and st.hi > st.lo:
                    ax.plot(
                        [c, c],
                        [st.lo, st.hi],
                        color=t["series"][ctrl_label],
                        linewidth=1,
                        alpha=0.6,
                        zorder=2,
                    )
        if ts is not None and ts[1][key] is not None:
            c, st = ts[0], ts[1][key]
            assert st is not None
            ax.plot(
                [c],
                [st.mean],
                color=t["series"][ts_label],
                linestyle="none",
                marker="D",
                markersize=8,
                markeredgecolor=t["surface"],
                markeredgewidth=2,
                label=f"{ts_label} @ c={c}",
                zorder=4,
            )
            if st.hi > st.lo:
                ax.plot([c, c], [st.lo, st.hi], color=t["series"][ts_label], linewidth=1, alpha=0.6, zorder=2)
        ax.set_xscale("log", base=2)
        ax.set_xticks(xs)
        ax.set_xticklabels([str(c) for c in xs])
        ax.set_xlabel("concurrency (trajectories in flight)", fontsize=8)
        ax.set_title(label, fontsize=10, loc="left", pad=8, color=t["ink"])
        ts_stat = ts[1][key] if ts else None
        top = max([st.hi for _, st in pts if st] + [ts_stat.hi if ts_stat else 0.0])
        ax.set_ylim(0, 1.05 if key == "cache_hit_rate" else top * 1.15 or 1.0)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=len(labels),
        frameon=False,
        fontsize=8,
        labelcolor=t["ink2"],
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.suptitle(
        "Agent replay on one RTX 4090 · Qwen3-8B-FP8 · SGLang 0.5.20 · 25 trajectories · real timing"
        " · n=3 (mean, min–max)",
        fontsize=9,
        color=t["muted"],
        x=0.01,
        ha="left",
        y=1.02,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    written = [_save(fig, out, "w4-concurrency", theme, t)]
    if theme == "light":
        rows = [
            {"experiment": f"w4-c{c}", "transform": "identity", "concurrency": c, **_flat(s)}
            for c, s in sweep
        ]
        if ts is not None:
            rows.append(
                {
                    "experiment": W4_TIMESTAMP,
                    "transform": "system_timestamp",
                    "concurrency": ts[0],
                    **_flat(ts[1]),
                }
            )
        written.append(_csv(out / "w4-concurrency.csv", rows))
    return written


# ── figure 2: W3 transforms ───────────────────────────────────────────────


def render_transforms(exp_dir: Path, out: Path, theme: str) -> list[Path]:
    t = THEMES[theme]
    groups: list[tuple[str, str, dict[str, Stat | None]]] = []
    for name, label in W3_GROUPS:
        runs = load_runs(exp_dir / name)
        if not runs:
            log.warning("no finished runs, skipped", exp=name)
            continue
        groups.append((name, label, group_stats(runs)))
    if not groups:
        return []

    keys = [m for m in METRICS if m[0] != "evicted_mtok"]
    fig, axes = _fig(len(keys), t, 12.0, 2.8)
    labels = [label for _, label, _ in groups][::-1]  # control on top
    ypos = list(range(len(groups)))
    for ax, (key, title, _) in zip(axes, keys, strict=True):
        _style(ax, t, ygrid=False)
        for y, (_, label, s) in zip(ypos, groups[::-1], strict=True):
            st = s[key]
            if st is None:
                continue
            ax.barh(y, st.mean, height=0.3, color=t["series"][label], zorder=3)
            if st.hi > st.lo:
                ax.plot([st.lo, st.hi], [y, y], color=t["ink2"], linewidth=1, alpha=0.7, zorder=4)
            text = f"{st.mean:.3f}" if key == "cache_hit_rate" else f"{st.mean:.1f} s"
            ax.text(st.hi, y, f"  {text}", fontsize=8, color=t["ink2"], ha="left", va="center")
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_title(title, fontsize=10, loc="left", pad=8, color=t["ink"])
        right = max(st.hi for _, _, s in groups if (st := s[key]) is not None)
        if key == "cache_hit_rate":
            ax.set_xlim(0, 1.18)
            ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        else:
            ax.set_xlim(0, right * 1.18)
        ax.spines["left"].set_visible(False)
    fig.suptitle(
        "Context transforms, single trajectory in flight · same 25 trajectories · compressed timing"
        " · n=3 (mean, min–max)",
        fontsize=9,
        color=t["muted"],
        x=0.01,
        ha="left",
        y=1.02,
    )
    fig.tight_layout()
    written = [_save(fig, out, "w3-transforms", theme, t)]
    if theme == "light":
        rows = [
            {"experiment": name, "transform": label, "concurrency": 1, **_flat(s)}
            for name, label, s in groups
        ]
        written.append(_csv(out / "w3-transforms.csv", rows))
    return written


# ── figure 3: W5 follow-ups ───────────────────────────────────────────────


@dataclass
class Dist:
    stats: dict[str, Stat | None]  # p50 / p95 / p99 / max, seconds
    censored: dict[str, bool]  # any run's value at that point is a timeout lower bound


def _dist(runs: list[Run], field: str) -> Dist:
    stats: dict[str, Stat | None] = {}
    flags: dict[str, bool] = {}
    for q, _, _ in W5_MARKS:
        stats[q] = _stat([_sec(dig(r.summary, ("all", field, q))) for r in runs])
        flags[q] = any(censored(r.summary, ("all", field, q)) for r in runs)
    return Dist(stats, flags)


def _fmt_s(v: float) -> str:
    return f"{v:.2f} s" if v < 1 else f"{v:.1f} s" if v < 100 else f"{v:.0f} s"


def render_w5(exp_dir: Path, out: Path, theme: str) -> list[Path]:
    t = THEMES[theme]
    rows: list[tuple[str, str, str, str, Stat | None, Dist, Dist]] = []
    for block, groups in W5_BLOCKS:
        for name, label, series in groups:
            runs = load_runs(exp_dir / name)
            if not runs:
                log.warning("no finished runs, skipped", exp=name)
                continue
            hit = _stat([dig(r.summary, ("all", "cache_hit_rate")) for r in runs])
            rows.append((block, name, label, series, hit, _dist(runs, "ttft_ms"), _dist(runs, "latency_ms")))
    if not rows:
        return []

    # top-to-bottom, with a gap between concurrency blocks
    ys: list[float] = []
    y, prev = 0.0, rows[0][0]
    for block, *_ in rows:
        if block != prev:
            y -= 0.6
            prev = block
        ys.append(y)
        y -= 1.0
    seps = [(ys[i - 1] + ys[i]) / 2 for i in range(1, len(rows)) if rows[i][0] != rows[i - 1][0]]

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(13.0, 0.42 * len(rows) + 1.6),
        facecolor=t["surface"],
        gridspec_kw={"width_ratios": [1.0, 1.6, 1.6]},
    )
    ax_hit, *ax_lat = list(axes)

    _style(ax_hit, t, ygrid=False)
    for y, (_, _, _, series, hit, _, _) in zip(ys, rows, strict=True):
        if hit is None:
            continue
        ax_hit.barh(y, hit.mean, height=0.5, color=t["series"][series], zorder=3)
        if hit.hi > hit.lo:
            ax_hit.plot([hit.lo, hit.hi], [y, y], color=t["ink2"], linewidth=1, alpha=0.7, zorder=4)
        ax_hit.text(hit.hi, y, f"  {hit.mean:.3f}", fontsize=8, color=t["ink2"], ha="left", va="center")
    ax_hit.set_xlim(0, 1.2)
    ax_hit.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax_hit.set_yticks(ys)
    ax_hit.set_yticklabels([f"{block}  {label}" for block, _, label, *_ in rows], fontsize=8)
    ax_hit.set_title("Cache hit rate", fontsize=10, loc="left", pad=8, color=t["ink"])
    ax_hit.spines["left"].set_visible(False)

    for ax, idx, title in ((ax_lat[0], 5, "TTFT (s, log)"), (ax_lat[1], 6, "Turn latency (s, log)")):
        _style(ax, t, ygrid=False)
        for y, row in zip(ys, rows, strict=True):
            dist: Dist = row[idx]  # type: ignore[assignment]
            color = t["series"][row[3]]
            pts = [(q, m, st) for q, m, _ in W5_MARKS if (st := dist.stats[q]) is not None]
            if not pts:
                continue
            ax.plot([pts[0][2].mean, pts[-1][2].mean], [y, y], color=color, linewidth=2, alpha=0.45, zorder=2)
            for q, marker, st in pts:
                hollow = dist.censored[q]
                ax.plot(
                    [st.mean],
                    [y],
                    linestyle="none",
                    marker=marker,
                    markersize=8,
                    color=color,
                    markerfacecolor=t["surface"] if hollow else color,
                    markeredgecolor=color if hollow else t["surface"],
                    markeredgewidth=2 if hollow else 1.5,
                    zorder=3,
                )
            first, last = pts[0], pts[-1]
            ax.text(
                first[2].mean / 1.25,
                y,
                _fmt_s(first[2].mean),
                fontsize=7.5,
                color=t["ink2"],
                ha="right",
                va="center",
            )
            cens = "≥ " if dist.censored[last[0]] else ""
            ax.text(
                last[2].mean * 1.25,
                y,
                cens + _fmt_s(last[2].mean),
                fontsize=7.5,
                color=t["ink2"],
                ha="left",
                va="center",
            )
        ax.set_xscale("log")
        ax.set_xlim(0.05, 5000)
        ax.set_xticks([0.1, 1, 10, 100, 1000])
        ax.set_xticklabels(["0.1", "1", "10", "100", "1000"])
        ax.set_yticks(ys)
        ax.set_yticklabels([])
        ax.set_title(title, fontsize=10, loc="left", pad=8, color=t["ink"])
        ax.spines["left"].set_visible(False)
    for ax in axes:
        for s_ in seps:
            ax.axhline(s_, color=t["grid"], linewidth=1.0, zorder=1)
        ax.set_ylim(min(ys) - 0.7, max(ys) + 0.7)

    handles = [
        Line2D([], [], linestyle="none", marker=m, markersize=7, color=t["ink2"], label=lab)
        for _, m, lab in W5_MARKS
    ]
    handles.append(
        Line2D(
            [],
            [],
            linestyle="none",
            marker="^",
            markersize=7,
            color=t["ink2"],
            markerfacecolor=t["surface"],
            markeredgewidth=1.5,
            label="hollow: ≥ (600 s client timeout)",
        )
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        fontsize=8,
        labelcolor=t["ink2"],
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.suptitle(
        "W5 follow-ups, each block vs its own re-run control · one RTX 4090 · Qwen3-8B-FP8 · SGLang 0.5.20"
        " · real timing · n=3 (mean; hit-rate bar shows min–max)",
        fontsize=9,
        color=t["muted"],
        x=0.01,
        ha="left",
        y=1.02,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    written = [_save(fig, out, "w5-followups", theme, t)]
    if theme == "light":
        csv_rows: list[dict[str, Any]] = []
        for block, name, label, _, hit, ttft, lat in rows:
            stats: dict[str, Stat | None] = {"cache_hit_rate": hit}
            stats.update({f"ttft_{q}_s": ttft.stats[q] for q, _, _ in W5_MARKS})
            stats.update({f"latency_{q}_s": lat.stats[q] for q, _, _ in W5_MARKS})
            csv_rows.append(
                {
                    "experiment": name,
                    "group": label,
                    "concurrency": block.removeprefix("c="),
                    **_flat(stats),
                    "ttft_max_censored": ttft.censored["max"],
                    "latency_max_censored": lat.censored["max"],
                }
            )
        written.append(_csv(out / "w5-followups.csv", csv_rows))
    return written


# ── output ────────────────────────────────────────────────────────────────


def _flat(s: dict[str, Stat | None]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, st in s.items():
        row[f"{key}_mean"] = None if st is None else round(st.mean, 4)
        row[f"{key}_min"] = None if st is None else round(st.lo, 4)
        row[f"{key}_max"] = None if st is None else round(st.hi, 4)
        row[f"{key}_n"] = 0 if st is None else st.n
    return row


def _csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def _save(fig: Any, out: Path, stem: str, theme: str, t: dict[str, Any]) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / (f"{stem}.png" if theme == "light" else f"{stem}-{theme}.png")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=t["surface"])
    plt.close(fig)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments-dir", type=Path, default=REPO_ROOT / "experiments")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "figures")
    args = ap.parse_args(argv)
    configure()
    written: list[Path] = []
    for theme in THEMES:
        written += render_concurrency(args.experiments_dir, args.out, theme)
        written += render_transforms(args.experiments_dir, args.out, theme)
        written += render_w5(args.experiments_dir, args.out, theme)
    for p in written:
        log.info("wrote figure", path=str(p))
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
