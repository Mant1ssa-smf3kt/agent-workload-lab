import asyncio
import json
from pathlib import Path

from replay.artifact import ArtifactWriter
from replay.config import Config, ReplayConfig
from replay.resummarize import main
from replay.scheduler import StepResult
from replay.tests.test_artifact import sr


def test_step_result_roundtrip() -> None:
    r = sr("t", 3, 100, 50, 12.5, error="ReadTimeout: ")
    r.recorded = {"prompt_tokens": 100}
    back = StepResult.from_dict(json.loads(json.dumps(r.to_dict())))
    assert back == r


def test_resummarize_rebuilds_from_requests(tmp_path: Path) -> None:
    exps = tmp_path / "experiments"
    run = exps / "e" / "out" / "20260920T000000"
    w = ArtifactWriter(run)
    cfg = Config(name="e", replay=ReplayConfig(concurrency=8))
    w.write_config(cfg)
    results = [sr("a", i, 100, 90, 100.0 + i) for i in range(4)]
    stalled = sr("a", 4, 0, 0, 0.0, error="ReadTimeout: ")
    stalled.result.ttft_ms = None
    stalled.result.prompt_tokens = None
    stalled.result.cached_tokens = None
    stalled.result.latency_ms = 600_000.0
    for r in [*results, stalled]:
        asyncio.run(w.on_result(r))
    w.close()
    old = {"wall_s": 123.4, "n_errors": 1, "all": {"latency_ms": {"p99": 206.0}}}
    (run / "summary.json").write_text(json.dumps(old))
    (run / "metrics_before.json").write_text(json.dumps({"metrics": {"sglang:cache_hit_rate": 0.5}}))
    (exps / "e" / "out" / "x-dry").mkdir()
    (exps / "e" / "out" / "broken").mkdir()

    assert main(["e", "--experiments-dir", str(exps)]) == 0
    new = json.loads((run / "summary.json").read_text())
    assert new["wall_s"] == 123.4 and new["concurrency"] == 8
    assert new["n_errors"] == 1 and new["n_timeouts"] == 1
    assert new["all"]["latency_ms"]["p99"] == 600_000.0 and new["all"]["latency_ms"]["p99_censored"]
    assert (
        new["metrics_before"]["sglang:cache_hit_rate"] == 0.5
        and new["metrics_after"]["sglang:cache_hit_rate"] is None
    )
    assert new["resummarized"]["from"] == "requests.jsonl"
    assert json.loads((run / "summary.prev.json").read_text()) == old

    # second pass keeps the original backup
    (run / "summary.json").write_text(json.dumps({"wall_s": 1.0}))
    assert main(["e", "--experiments-dir", str(exps)]) == 0
    assert json.loads((run / "summary.prev.json").read_text()) == old
    assert json.loads((run / "summary.json").read_text())["wall_s"] == 1.0

    assert main(["nope", "--experiments-dir", str(exps)]) == 2
