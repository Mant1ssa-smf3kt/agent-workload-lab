"""Artifact layout for one replay run and the summary computed from it.

    experiments/<name>/out/<run_id>/
      config.resolved.yaml   exact config used
      fingerprint.json       environment (serve fingerprint + replayer commit + trace sha256s)
      plan.json              every step before sending: gaps, max_tokens, payload sha
      requests.jsonl         one line per replayed request, appended as they finish
      metrics_before.json / metrics_after.json / metrics_samples.jsonl   SGLang /metrics
      summary.json           P50/P95/P99 and the §5 cache-hit rate

Every number reported anywhere must be derivable from these files (CLAUDE.md §8.4).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from analysis.stats import pct
from metrics.sglang import key_metrics
from replay.config import Config
from replay.scheduler import RunStats, StepResult
from replay.trajectory import Trajectory


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def git_info(cwd: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=5
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": head, "dirty": None if status is None else bool(status)}


def build_fingerprint(
    cfg: Config,
    config_path: Path,
    serve_fingerprint: dict[str, Any] | None,
    trajectories: list[Trajectory],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "replayer": {**git_info(repo_root), "python": sys.version.split()[0], "httpx": httpx.__version__},
        "config_path": str(config_path),
        "config_sha256": sha256_json(cfg.to_dict()),
        "serve": serve_fingerprint,
        "gpu": (serve_fingerprint or {}).get("gpu"),
        "sglang_version": (serve_fingerprint or {}).get("sglang_version"),
        "model": (serve_fingerprint or {}).get("model"),
        "pi_versions": sorted({t.pi_version for t in trajectories}),
        "extension_versions": sorted({t.extension_version for t in trajectories}),
        "traces": [
            {
                "id": t.id,
                "path": str(t.path),
                "sha256": sha256_file(t.path),
                "session_id": t.session_id,
                "recorded_model": t.recorded_model,
                "n_steps": len(t.steps),
                "n_synthetic": t.n_synthetic,
                "dropped_requests": t.dropped_requests,
                "dropped_keys": t.dropped_keys,
            }
            for t in trajectories
        ],
    }


def build_plan(trajectories: list[Trajectory], cfg: Config) -> dict[str, Any]:
    from replay.scheduler import planned_gap_ms

    return {
        "timing": cfg.replay.timing,
        "concurrency": cfg.replay.concurrency,
        "n_trajectories": len(trajectories),
        "n_steps": sum(len(t.steps) for t in trajectories),
        "n_synthetic": sum(t.n_synthetic for t in trajectories),
        "planned_gap_total_s": sum(planned_gap_ms(s, cfg) for t in trajectories for s in t.steps) / 1000.0,
        "trajectories": [
            {
                "id": t.id,
                "steps": [
                    {
                        "idx": s.idx,
                        "kind": s.kind,
                        "run": s.run,
                        "turn": s.turn,
                        "req": s.req,
                        "gap_before_ms": s.gap_before_ms,
                        "gap_planned_ms": planned_gap_ms(s, cfg),
                        "max_tokens": s.payload.get("max_tokens"),
                        "n_messages": len(s.payload.get("messages", [])),
                        "payload_sha256": sha256_json(s.payload),
                        "recorded_prompt_tokens": s.recorded.prompt_tokens,
                        "recorded_output_tokens": s.recorded.output_tokens,
                    }
                    for s in t.steps
                ],
            }
            for t in trajectories
        ],
    }


def _agg(rs: list[StepResult]) -> dict[str, Any]:
    with_usage = [r for r in rs if r.result.prompt_tokens is not None]
    prompt = sum(r.result.prompt_tokens or 0 for r in with_usage)
    cached = sum(r.result.cached_tokens or 0 for r in with_usage)
    ratios = [
        (r.result.cached_tokens or 0) / r.result.prompt_tokens for r in with_usage if r.result.prompt_tokens
    ]
    return {
        "n": len(rs),
        "n_with_usage": len(with_usage),
        "prompt_tokens_total": prompt,
        "cached_tokens_total": cached,
        # CLAUDE.md §5: hit prefill tokens / total prefill tokens, aggregated over requests.
        "cache_hit_rate": (cached / prompt) if prompt else None,
        "cache_hit_per_request": pct(ratios),
        "ttfb_ms": pct(r.result.ttfb_ms for r in rs),
        "ttft_ms": pct(r.result.ttft_ms for r in rs),
        "latency_ms": pct(r.result.latency_ms for r in rs),
        "prompt_tokens": pct(r.result.prompt_tokens for r in rs),
        "completion_tokens": pct(r.result.completion_tokens for r in rs),
        "gap_actual_ms": pct(r.gap_actual_ms for r in rs if r.idx > 0),
    }


def summarize(
    stats: RunStats,
    cfg: Config,
    metrics_before: dict[str, Any] | None,
    metrics_after: dict[str, Any] | None,
) -> dict[str, Any]:
    measured = [r for r in stats.results if not r.warmup]
    ok = [r for r in measured if r.result.error is None]
    errors = [r for r in measured if r.result.error is not None]
    real = [r for r in ok if not r.synthetic]
    per_traj: dict[str, dict[str, Any]] = {}
    for tid in sorted({r.trajectory for r in ok}):
        per_traj[tid] = _agg([r for r in ok if r.trajectory == tid])
    return {
        "name": cfg.name,
        "timing": cfg.replay.timing,
        "concurrency": cfg.replay.concurrency,
        "transform": cfg.transform.name,
        "wall_s": None if stats.finished_epoch is None else stats.finished_epoch - stats.started_epoch,
        "n_results": len(stats.results),
        "n_warmup": len(stats.results) - len(measured),
        "n_errors": len(errors),
        "error_samples": [r.result.error for r in errors[:5]],
        "all": _agg(ok),
        "excluding_synthetic": _agg(real),
        "per_trajectory": per_traj,
        "metrics_before": key_metrics((metrics_before or {}).get("metrics", {})),
        "metrics_after": key_metrics((metrics_after or {}).get("metrics", {})),
    }


class ArtifactWriter:
    def __init__(self, out_dir: Path) -> None:
        self.dir = out_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._requests = (self.dir / "requests.jsonl").open("a", encoding="utf-8")

    def write_json(self, name: str, obj: Any) -> None:
        (self.dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_config(self, cfg: Config) -> None:
        (self.dir / "config.resolved.yaml").write_text(
            yaml.safe_dump(cfg.to_dict(), allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    async def on_result(self, r: StepResult) -> None:
        self._requests.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
        self._requests.flush()

    def close(self) -> None:
        self._requests.close()
