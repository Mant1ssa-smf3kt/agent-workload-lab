"""Replay CLI.

    uv run python -m replay.run experiments/<name>/config.yaml --dry-run   # no network, no GPU
    uv run python -m replay.run experiments/<name>/config.yaml             # needs SGLang up (GPU)

Dry-run builds every step (payload normalization, gaps, synthetic compactions) and writes
plan.json + fingerprint.json into ``<out>/<run_id>-dry/``. A real run additionally requires
the serve fingerprint file (CLAUDE.md §9) and a reachable server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from analysis.log import configure, get_logger
from metrics.sglang import Sampler, snapshot
from replay.artifact import ArtifactWriter, build_fingerprint, build_plan, summarize
from replay.client import ChatClient
from replay.config import Config, ConfigError, load_config, resolve_out_dir
from replay.scheduler import run_replay
from replay.trajectory import LoadReport, load_trajectories

log = get_logger("replay.run")
REPO_ROOT = Path(__file__).resolve().parents[1]

# Test hook: when set, both the chat client and the metrics client use this transport.
_TRANSPORT: httpx.AsyncBaseTransport | None = None


def _run_id(dry: bool) -> str:
    return time.strftime("%Y%m%dT%H%M%S") + ("-dry" if dry else "")


def _load_serve_fingerprint(cfg: Config) -> dict[str, Any] | None:
    if not cfg.fingerprint:
        return None
    p = Path(cfg.fingerprint).expanduser()
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def prepare(config_path: Path, dry: bool, out_override: Path | None) -> tuple[Config, LoadReport, Path]:
    cfg = load_config(config_path)
    report = load_trajectories(cfg, REPO_ROOT)
    for s in report.skipped:
        log.warning("skipped trace", reason=s)
    out_dir = (out_override or resolve_out_dir(cfg, config_path)) / _run_id(dry)
    return cfg, report, out_dir


async def _main(config_path: Path, dry: bool, out_override: Path | None) -> int:
    cfg, report, out_dir = prepare(config_path, dry, out_override)
    trajs = report.trajectories
    if not trajs:
        log.error("no trajectories to replay", skipped=report.skipped)
        return 2

    serve_fp = _load_serve_fingerprint(cfg)
    if not dry and serve_fp is None:
        log.error(
            "serve fingerprint missing; artifact would be invalid (CLAUDE.md §9)",
            fingerprint=cfg.fingerprint,
        )
        return 2

    writer = ArtifactWriter(out_dir)
    writer.write_config(cfg)
    writer.write_json("fingerprint.json", build_fingerprint(cfg, config_path, serve_fp, trajs, REPO_ROOT))
    plan = build_plan(trajs, cfg)
    writer.write_json("plan.json", plan)
    log.info(
        "plan",
        out=str(out_dir),
        trajectories=plan["n_trajectories"],
        steps=plan["n_steps"],
        synthetic=plan["n_synthetic"],
        planned_gap_total_s=round(plan["planned_gap_total_s"], 1),
        timing=cfg.replay.timing,
        concurrency=cfg.replay.concurrency,
        dropped_keys=sorted({k for t in trajs for k in t.dropped_keys}),
    )
    if dry:
        writer.close()
        log.info("dry-run complete", out=str(out_dir))
        return 0

    client = ChatClient(cfg.server.base_url, cfg.server.api_key, cfg.server.timeout_s, transport=_TRANSPORT)
    http = httpx.AsyncClient(timeout=10.0, transport=_TRANSPORT)
    try:
        try:
            models = await client.models()
        except (httpx.HTTPError, OSError) as e:
            log.error("server unreachable", base_url=cfg.server.base_url, error=str(e))
            return 2
        if cfg.server.model not in models:
            log.error("served model mismatch", want=cfg.server.model, served=models)
            return 2

        before = await snapshot(http, cfg.server.metrics_url) if cfg.server.metrics_url else None
        writer.write_json("metrics_before.json", before)
        sampler: Sampler | None = None
        if cfg.server.metrics_url:
            sampler = Sampler(http, cfg.server.metrics_url, out_dir / "metrics_samples.jsonl")
            sampler.start()

        log.info("replay start", trajectories=len(trajs))
        stats = await run_replay(trajs, cfg, client, on_result=writer.on_result)

        if sampler is not None:
            await sampler.stop()
            log.info("metrics sampler", ok=sampler.n_ok, errors=sampler.n_err)
        after = await snapshot(http, cfg.server.metrics_url) if cfg.server.metrics_url else None
        writer.write_json("metrics_after.json", after)

        summary = summarize(stats, cfg, before, after)
        writer.write_json("summary.json", summary)
        log.info(
            "replay done",
            out=str(out_dir),
            wall_s=round(summary["wall_s"] or 0, 1),
            n=summary["all"]["n"],
            errors=summary["n_errors"],
            cache_hit_rate=summary["all"]["cache_hit_rate"],
            ttft_p50_ms=summary["all"]["ttft_ms"]["p50"],
            ttft_p95_ms=summary["all"]["ttft_ms"]["p95"],
        )
        return 0 if summary["n_errors"] == 0 else 1
    finally:
        writer.close()
        await client.aclose()
        await http.aclose()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="build the plan only; no network")
    ap.add_argument("--out", type=Path, default=None, help="override artifact root")
    args = ap.parse_args(argv)
    configure()
    try:
        return asyncio.run(_main(args.config, args.dry_run, args.out))
    except ConfigError as e:
        log.error("config error", error=str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
