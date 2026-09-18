"""Percentile helpers. Tail latency is always P50/P95/P99 — never mean-only (CLAUDE.md §5)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import TypedDict


class Pct(TypedDict):
    n: int
    p50: float | None
    p95: float | None
    p99: float | None
    min: float | None
    max: float | None


def percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile on an already-sorted, non-empty list. ``p`` in [0, 100]."""
    if not sorted_values:
        raise ValueError("percentile of empty list")
    k = max(1, math.ceil(p / 100 * len(sorted_values)))
    return sorted_values[k - 1]


def pct(values: Iterable[float | int | None]) -> Pct:
    """P50/P95/P99/min/max of the non-None values. ``n`` counts only those."""
    xs = sorted(float(v) for v in values if v is not None)
    if not xs:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "min": None, "max": None}
    return {
        "n": len(xs),
        "p50": percentile(xs, 50),
        "p95": percentile(xs, 95),
        "p99": percentile(xs, 99),
        "min": xs[0],
        "max": xs[-1],
    }


def fmt_pct(p: Pct, unit: str = "", digits: int = 0) -> str:
    """``p50 / p95 / p99 (n)`` for tables; ``—`` when empty."""
    if p["n"] == 0:
        return "—"

    def f(v: float | None) -> str:
        return "—" if v is None else f"{v:.{digits}f}{unit}"

    return f"{f(p['p50'])} / {f(p['p95'])} / {f(p['p99'])} (n={p['n']})"
