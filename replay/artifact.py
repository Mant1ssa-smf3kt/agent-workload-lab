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

from analysis.stats import pct, pct_censored
from metrics.sglang import key_metrics
from replay.client import RequestResult
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
    # Tracked files only, like `git describe --dirty`: an untracked artifact must not mark the code dirty.
    status = run("status", "--porcelain", "--untracked-files=no")
    if head is not None:
        return {"commit": head, "dirty": bool(status), "source": "git"}
    # Remote checkouts are rsynced without .git; scripts/sync.sh leaves .sync-commit behind.
    marker = cwd / ".sync-commit"
    if marker.exists():
        kv = dict(line.split("=", 1) for line in marker.read_text().splitlines() if "=" in line)
        commit = kv.get("commit")
        return {
            "commit": None if commit in (None, "unknown") else commit,
            "dirty": kv.get("dirty") == "true",
            "source": "sync-commit",
            "synced_at": kv.get("synced_at"),
        }
    return {"commit": None, "dirty": None, "source": None}


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


# Client-side stalls: the request was still queued/streaming when we gave up at timeout_s, so its
# TTFT/latency are unknown but ≥ the time we waited. Kept in the tail as right-censored bounds.
CENSORING_ERRORS = ("ReadTimeout", "WriteTimeout")


def is_timeout(res: RequestResult) -> bool:
    return res.error is not None and res.error.split(":", 1)[0] in CENSORING_ERRORS


def _agg(rs: list[StepResult], timed_out: list[StepResult]) -> dict[str, Any]:
    with_usage = [r for r in rs if r.result.prompt_tokens is not None]
    prompt = sum(r.result.prompt_tokens or 0 for r in with_usage)
    cached = sum(r.result.cached_tokens or 0 for r in with_usage)
    ratios = [
        (r.result.cached_tokens or 0) / r.result.prompt_tokens for r in with_usage if r.result.prompt_tokens
    ]

    def censored(attr: str) -> list[tuple[float | None, bool]]:
        pairs: list[tuple[float | None, bool]] = [(getattr(r.result, attr), False) for r in rs]
        for r in timed_out:
            v = getattr(r.result, attr)
            # a stall after the first token leaves ttfb/ttft exact and only latency censored
            pairs.append(
                (v, False) if v is not None and attr != "latency_ms" else (r.result.latency_ms, True)
            )
        return pairs

    return {
        "n": len(rs),
        "n_with_usage": len(with_usage),
        "n_censored": len(timed_out),
        "prompt_tokens_total": prompt,
        "cached_tokens_total": cached,
        # CLAUDE.md §5: hit prefill tokens / total prefill tokens, aggregated over requests.
        "cache_hit_rate": (cached / prompt) if prompt else None,
        "cache_hit_per_request": pct(ratios),
        "ttfb_ms": pct_censored(censored("ttfb_ms")),
        "ttft_ms": pct_censored(censored("ttft_ms")),
        "latency_ms": pct_censored(censored("latency_ms")),
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
    timed_out = [r for r in errors if is_timeout(r.result)]
    real = [r for r in ok if not r.synthetic]
    real_timed_out = [r for r in timed_out if not r.synthetic]
    per_traj: dict[str, dict[str, Any]] = {}
    for tid in sorted({r.trajectory for r in [*ok, *timed_out]}):
        per_traj[tid] = _agg(
            [r for r in ok if r.trajectory == tid], [r for r in timed_out if r.trajectory == tid]
        )
    km_before = key_metrics((metrics_before or {}).get("metrics", {}))
    km_after = key_metrics((metrics_after or {}).get("metrics", {}))
    return {
        "name": cfg.name,
        "timing": cfg.replay.timing,
        "concurrency": cfg.replay.concurrency,
        "transform": cfg.transform.name,
        "timeout_s": cfg.server.timeout_s,
        "wall_s": None if stats.finished_epoch is None else stats.finished_epoch - stats.started_epoch,
        "n_results": len(stats.results),
        "n_warmup": len(stats.results) - len(measured),
        "n_errors": len(errors),
        "n_timeouts": len(timed_out),
        "error_samples": [r.result.error for r in errors[:5]],
        "all": _agg(ok, timed_out),
        "excluding_synthetic": _agg(real, real_timed_out),
        "per_trajectory": per_traj,
        "metrics_before": km_before,
        "metrics_after": km_after,
        "server_delta": server_delta(km_before, km_after),
    }


# Server-side counters over the run = after − before. None when either snapshot lacks the value
# (a failed snapshot is a missing value, CLAUDE.md §10). The server is not restarted between runs,
# so the raw counters are cumulative over the session and only the difference belongs to this run.
SERVER_DELTAS = {
    "evicted_tokens": "sglang:evicted_tokens_total",
    "retracted_requests": "sglang:num_retracted_requests_total",
    "retracted_input_tokens": "sglang:num_retracted_input_tokens_total",
}


def server_delta(before: dict[str, float | None], after: dict[str, float | None]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, metric in SERVER_DELTAS.items():
        b, a = before.get(metric), after.get(metric)
        out[key] = None if a is None or b is None else a - b
    return out


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
