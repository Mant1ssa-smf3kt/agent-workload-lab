"""Rebuild ``summary.json`` of finished runs from ``requests.jsonl`` (``just resummarize EXP...``).

For when the summary definition changes (docs/decisions.md) but the raw per-request artifact is
intact. The previous summary is kept as ``summary.prev.json`` (first one wins); ``wall_s`` is
carried over because it is measured, not derived.

    uv run python -m replay.resummarize w4-c8 w4-c4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from analysis.log import configure, get_logger
from replay.artifact import git_info, summarize
from replay.config import load_config
from replay.scheduler import RunStats, StepResult

log = get_logger("replay.resummarize")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_json(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def resummarize_run(run_dir: Path) -> bool:
    requests, cfg_path, prev_path = (
        run_dir / "requests.jsonl",
        run_dir / "config.resolved.yaml",
        run_dir / "summary.json",
    )
    if not (requests.exists() and cfg_path.exists() and prev_path.exists()):
        log.warning("incomplete run skipped", run=str(run_dir))
        return False
    prev = _read_json(prev_path) or {}
    cfg = load_config(cfg_path)
    stats = RunStats(started_epoch=0.0, finished_epoch=prev.get("wall_s"))
    with requests.open(encoding="utf-8") as f:
        stats.results = [StepResult.from_dict(json.loads(line)) for line in f if line.strip()]
    summary = summarize(
        stats, cfg, _read_json(run_dir / "metrics_before.json"), _read_json(run_dir / "metrics_after.json")
    )
    summary["resummarized"] = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "replayer": git_info(REPO_ROOT),
        "from": "requests.jsonl",
    }
    backup = run_dir / "summary.prev.json"
    if not backup.exists():
        backup.write_text(prev_path.read_text(encoding="utf-8"), encoding="utf-8")
    prev_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "resummarized",
        run=str(run_dir),
        n_errors=summary["n_errors"],
        n_timeouts=summary["n_timeouts"],
        latency_p99_ms=summary["all"]["latency_ms"]["p99"],
        latency_p99_censored=summary["all"]["latency_ms"]["p99_censored"],
    )
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp", nargs="+", help="experiment names under experiments/")
    ap.add_argument("--experiments-dir", type=Path, default=REPO_ROOT / "experiments")
    args = ap.parse_args(argv)
    configure()
    rc = 0
    for exp in args.exp:
        out = args.experiments_dir / exp / "out"
        if not out.exists():
            log.error("experiment has no out/", exp=exp)
            rc = 2
            continue
        for d in sorted(out.iterdir()):
            if d.is_dir() and not d.name.endswith("-dry"):
                resummarize_run(d)
    return rc


if __name__ == "__main__":
    sys.exit(main())
