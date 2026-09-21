import json
from pathlib import Path

from replay.artifact import ArtifactWriter, build_fingerprint, build_plan, summarize
from replay.client import RequestResult
from replay.config import Config, ReplayConfig
from replay.scheduler import RunStats, StepResult
from replay.trajectory import Recorded, Step, Trajectory


def sr(
    tid: str,
    idx: int,
    prompt: int,
    cached: int,
    ttft: float,
    *,
    synthetic: bool = False,
    warmup: bool = False,
    error: str | None = None,
) -> StepResult:
    res = RequestResult(
        t_send_epoch=0.0,
        ttft_ms=ttft,
        latency_ms=ttft * 2,
        prompt_tokens=prompt,
        cached_tokens=cached,
        error=error,
    )
    return StepResult(
        tid,
        idx,
        "compaction" if synthetic else "request",
        0,
        idx,
        idx,
        synthetic,
        warmup,
        0,
        0.0,
        0.0,
        {},
        res,
    )


def test_summary_cache_hit_is_sum_ratio_not_mean_of_ratios() -> None:
    cfg = Config(name="x", replay=ReplayConfig(timing="compressed", concurrency=2))
    stats = RunStats(started_epoch=0.0, finished_epoch=10.0)
    stats.results = [
        sr("a", 0, 100, 0, 10.0),
        sr("a", 1, 1000, 900, 20.0),  # big request dominates the §5 aggregate
        sr("b", 0, 100, 100, 30.0, synthetic=True),
        sr("b", 1, 100, 0, 5.0, warmup=True),
        sr("b", 2, 100, 0, 5.0, error="HTTP 500"),
    ]
    s = summarize(stats, cfg, None, None)
    assert (
        s["n_results"] == 5
        and s["n_warmup"] == 1
        and s["n_errors"] == 1
        and s["error_samples"] == ["HTTP 500"]
    )
    a = s["all"]
    assert a["n"] == 3 and a["prompt_tokens_total"] == 1200 and a["cached_tokens_total"] == 1000
    assert abs(a["cache_hit_rate"] - 1000 / 1200) < 1e-9
    assert a["cache_hit_per_request"]["p50"] == 0.9  # ratios 0, 0.9, 1.0 → nearest-rank P50 = 0.9
    assert a["ttft_ms"]["p50"] == 20.0 and a["ttft_ms"]["p99"] == 30.0 and a["latency_ms"]["p50"] == 40.0
    ex = s["excluding_synthetic"]
    assert (
        ex["n"] == 2 and ex["prompt_tokens_total"] == 1100 and abs(ex["cache_hit_rate"] - 900 / 1100) < 1e-9
    )
    assert set(s["per_trajectory"]) == {"a", "b"} and s["per_trajectory"]["a"]["n"] == 2
    assert s["wall_s"] == 10.0 and s["timing"] == "compressed" and s["concurrency"] == 2
    assert s["metrics_before"]["sglang:cache_hit_rate"] is None


def test_summary_timeouts_are_right_censored_not_dropped() -> None:
    stats = RunStats(started_epoch=0.0, finished_epoch=10.0)
    ok = [sr("a", i, 100, 90, 100.0 + i) for i in range(9)]  # latency 200..216
    stalled = sr("a", 9, 0, 0, 0.0, error="ReadTimeout: ")
    stalled.result.ttft_ms = None
    stalled.result.ttfb_ms = None
    stalled.result.prompt_tokens = None
    stalled.result.cached_tokens = None
    stalled.result.latency_ms = 600_000.0
    failed = sr("b", 0, 100, 0, 5.0, error="HTTP 500")
    stats.results = [*ok, stalled, failed]
    cfg = Config(name="x")
    s = summarize(stats, cfg, None, None)

    assert s["n_errors"] == 2 and s["n_timeouts"] == 1 and s["timeout_s"] == cfg.server.timeout_s
    a = s["all"]
    # HTTP 500 is a failure, not a latency observation; the stall is a lower bound on the tail
    assert a["n"] == 9 and a["n_censored"] == 1 and a["n_with_usage"] == 9
    assert a["latency_ms"]["n"] == 10 and a["latency_ms"]["p99"] == 600_000.0
    assert a["latency_ms"]["p99_censored"] and not a["latency_ms"]["p50_censored"]
    assert a["ttft_ms"]["p99"] == 600_000.0 and a["ttft_ms"]["p99_censored"]
    assert a["ttfb_ms"]["p99"] == 600_000.0 and a["ttfb_ms"]["p99_censored"]
    # §5 hit rate stays over requests with usage only
    assert abs(a["cache_hit_rate"] - 0.9) < 1e-9
    assert s["per_trajectory"]["a"]["n_censored"] == 1 and "b" not in s["per_trajectory"]

    # a stall after the first token keeps ttft exact and censors only latency
    late = sr("a", 10, 0, 0, 50.0, error="ReadTimeout: ")
    late.result.latency_ms = 600_000.0
    stats.results = [*ok, late]
    a = summarize(stats, cfg, None, None)["all"]
    assert a["ttft_ms"]["max"] == 108.0 and not a["ttft_ms"]["p99_censored"]
    assert a["latency_ms"]["p99"] == 600_000.0 and a["latency_ms"]["p99_censored"]


def test_summary_with_metrics_and_no_usage() -> None:
    stats = RunStats(started_epoch=0.0, finished_epoch=1.0)
    r = sr("a", 0, 0, 0, 1.0)
    r.result.prompt_tokens = None
    r.result.cached_tokens = None
    stats.results = [r]
    before = {"t": 0, "metrics": {"sglang:cache_hit_rate{model_name=m}": 0.25, "sglang:other": 1}}
    s = summarize(stats, Config(name="x"), before, {"t": 1, "error": "down"})
    assert s["all"]["n_with_usage"] == 0 and s["all"]["cache_hit_rate"] is None
    assert (
        s["metrics_before"]["sglang:cache_hit_rate"] == 0.25
        and s["metrics_after"]["sglang:cache_hit_rate"] is None
    )


def test_plan_fingerprint_and_writer(tmp_path: Path) -> None:
    cfg = Config(name="x", replay=ReplayConfig(gap_scale=0.5))
    trace = tmp_path / "t.jsonl"
    trace.write_text("{}\n")
    t = Trajectory(
        id="t",
        path=trace,
        session_id="s",
        pi_version="0.85.1",
        extension_version="0.1.0",
        recorded_model="zai/glm-5.2",
    )
    rec = Recorded(100, 50, 7, 10, 20, 400)
    t.steps.append(Step("t", 0, "request", 0, 0, 0, 0, {"messages": [1], "max_tokens": 7}, rec))
    t.steps.append(
        Step(
            "t", 1, "compaction", 0, 0, None, 1000, {"messages": [1, 2], "max_tokens": 3}, rec, synthetic=True
        )
    )
    t.dropped_keys = ["thinking"]

    plan = build_plan([t], cfg)
    assert plan["n_steps"] == 2 and plan["n_synthetic"] == 1 and plan["planned_gap_total_s"] == 0.5
    assert plan["trajectories"][0]["steps"][1]["gap_planned_ms"] == 500
    assert (
        plan["trajectories"][0]["steps"][0]["max_tokens"] == 7
        and len(plan["trajectories"][0]["steps"][0]["payload_sha256"]) == 64
    )

    fp = build_fingerprint(
        cfg,
        tmp_path / "config.yaml",
        {"gpu": {"name": "RTX 4090"}, "sglang_version": "0.5.20"},
        [t],
        tmp_path,
    )
    assert fp["gpu"] == {"name": "RTX 4090"} and fp["sglang_version"] == "0.5.20"
    assert fp["pi_versions"] == ["0.85.1"] and fp["traces"][0]["dropped_keys"] == ["thinking"]
    assert len(fp["traces"][0]["sha256"]) == 64 and len(fp["config_sha256"]) == 64
    assert fp["replayer"]["commit"] is None and fp["replayer"]["source"] is None  # no git, no marker
    (tmp_path / ".sync-commit").write_text("commit=abc123\ndirty=true\nsynced_at=2026-09-18T00:00:00Z\n")
    rp = build_fingerprint(cfg, tmp_path / "config.yaml", None, [t], tmp_path)["replayer"]
    assert (rp["commit"], rp["dirty"], rp["source"], rp["synced_at"]) == (
        "abc123",
        True,
        "sync-commit",
        "2026-09-18T00:00:00Z",
    )

    w = ArtifactWriter(tmp_path / "out")
    w.write_config(cfg)
    w.write_json("plan.json", plan)
    import asyncio

    asyncio.run(w.on_result(sr("t", 0, 10, 5, 1.0)))
    w.close()
    assert (tmp_path / "out" / "config.resolved.yaml").read_text().startswith("name: x")
    lines = (tmp_path / "out" / "requests.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["res_cached_tokens"] == 5
