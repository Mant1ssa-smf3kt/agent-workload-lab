import json
from pathlib import Path
from typing import Any

import yaml

from analysis.report import (
    config_diff,
    env_consistent,
    load_runs,
    main,
    render_compare,
    render_variance,
    spread,
)


def make_run(
    exp_dir: Path,
    run_id: str,
    *,
    hit: float,
    ttft_p95: float,
    errors: int = 0,
    timeouts: int = 0,
    gpu: str = "RTX 4090",
    commit: str = "abc",
    config: dict[str, Any] | None = None,
) -> Path:
    d = exp_dir / "out" / run_id
    d.mkdir(parents=True)
    summary: dict[str, Any] = {
        "n_errors": errors,
        "wall_s": 100.0,
        "all": {
            "n": 173,
            "cache_hit_rate": hit,
            "prompt_tokens_total": 5_000_000,
            "ttft_ms": {"p50": 100.0, "p95": ttft_p95, "p99": ttft_p95 * 1.5},
            "latency_ms": {"p50": 1000.0, "p95": 3000.0, "p99": 4000.0},
        },
        "excluding_synthetic": {"cache_hit_rate": hit + 0.001},
    }
    if timeouts:
        summary["n_timeouts"] = timeouts
        summary["all"]["n_censored"] = timeouts  # a count next to "n", must not read as a ≥ flag
        summary["all"]["latency_ms"] = {"p50": 1000.0, "p95": 3000.0, "p99": 600_000.0, "p99_censored": True}
    fp = {
        "gpu": {"name": gpu, "driver": "580"},
        "sglang_version": "0.5.20",
        "model": {"id": "Qwen/Qwen3-8B-FP8"},
        "pi_versions": ["0.85.1"],
        "extension_versions": ["0.1.0"],
        "replayer": {"commit": commit, "dirty": False},
        "traces": [{"id": "a"}, {"id": "b"}],
    }
    cfg: dict[str, Any] = {
        "name": exp_dir.name,
        "replay": {"timing": "real", "concurrency": 1},
        "transform": {"name": "identity"},
    }
    for k, v in (config or {}).items():
        cfg.setdefault(k, {}).update(v)
    (d / "summary.json").write_text(json.dumps(summary))
    (d / "fingerprint.json").write_text(json.dumps(fp))
    (d / "config.resolved.yaml").write_text(yaml.safe_dump(cfg))
    return d


def test_spread() -> None:
    s = spread([1.0, 2.0, 3.0])
    assert s.n == 3 and s.mean == 2.0 and (s.lo, s.hi) == (1.0, 3.0)
    assert s.std is not None and abs(s.std - 1.0) < 1e-9
    assert s.cv is not None and abs(s.cv - 0.5) < 1e-9
    assert spread([None, 5.0]).std == 0.0 and spread([]).mean is None and spread([0.0]).cv is None


def test_load_runs_skips_dry_and_incomplete(tmp_path: Path) -> None:
    exp = tmp_path / "e"
    make_run(exp, "r1", hit=0.9, ttft_p95=500)
    (exp / "out" / "r0-dry").mkdir()
    (exp / "out" / "broken").mkdir()
    runs = load_runs(exp)
    assert [r.run_id for r in runs] == ["r1"] and runs[0].config["replay"]["concurrency"] == 1
    assert load_runs(tmp_path / "nope") == []


def test_variance_report_verdicts(tmp_path: Path) -> None:
    exp = tmp_path / "baseline-c1"
    make_run(exp, "r1", hit=0.90, ttft_p95=500)
    make_run(exp, "r2", hit=0.91, ttft_p95=520)
    md = render_variance("baseline-c1", load_runs(exp))
    assert "只有 2 次 run，方差未确认" in md
    assert "| cache hit rate | 0.9000 | 0.9100 |" in md
    assert "RTX 4090" in md and "0.5.20" in md and "concurrency=1" in md

    make_run(exp, "r3", hit=0.92, ttft_p95=480)
    md = render_variance("baseline-c1", load_runs(exp))
    assert "可用于对照" in md and "CV" in md

    make_run(exp, "r4", hit=0.5, ttft_p95=999, gpu="RTX 5090", errors=2)
    md = render_variance("baseline-c1", load_runs(exp))
    assert "指纹不一致" in md and "r4: gpu" in md and "2 个请求出错" in md and "本组无效" in md

    assert "没有完成的 run" in render_variance("x", [])


def test_variance_report_marks_censored_tail(tmp_path: Path) -> None:
    exp = tmp_path / "w4-c8"
    make_run(exp, "r1", hit=0.5, ttft_p95=500, config={"server": {"timeout_s": 600.0}})
    make_run(exp, "r2", hit=0.5, ttft_p95=500, errors=3, timeouts=3, config={"server": {"timeout_s": 600.0}})
    make_run(exp, "r3", hit=0.5, ttft_p95=500, errors=4, timeouts=3, config={"server": {"timeout_s": 600.0}})
    md = render_variance("w4-c8", load_runs(exp))
    assert "timeout_s=600" in md
    assert "| latency P99 | 4000 ms | ≥ 600000 ms | ≥ 600000 ms | ≥ 401333 ms ± 344101 ms |" in md
    assert "| ≥ 4000 ms – ≥ 600000 ms |" in md
    assert "| latency P95 | 3000 ms | 3000 ms | 3000 ms |" in md
    assert "| timeouts (censored) | — | 3 | 3 |" in md
    assert "| requests | 173 | 173 | 173 |" in md
    assert "`≥`：该分位落在超时请求上" in md
    # one non-timeout error still blocks; the timeouts are only a note
    assert "共 1 个请求出错（非超时）" in md and "6 个请求超时" in md and "可用于对照" not in md

    exp2 = tmp_path / "w4-c8b"
    for i in range(3):
        make_run(exp2, f"r{i}", hit=0.5, ttft_p95=500, errors=2, timeouts=2)
    md = render_variance("w4-c8b", load_runs(exp2))
    assert "6 个请求超时" in md and "可用于对照" in md and "无错误" not in md


def test_env_consistent_and_config_diff(tmp_path: Path) -> None:
    exp = tmp_path / "e"
    make_run(exp, "r1", hit=0.9, ttft_p95=1)
    make_run(exp, "r2", hit=0.9, ttft_p95=1, commit="def")
    ok, problems = env_consistent(load_runs(exp))
    assert not ok and problems and "replayer_commit" in problems[0]
    a = {"name": "a", "replay": {"concurrency": 1, "timing": "real"}, "notes": "x"}
    b = {"name": "b", "replay": {"concurrency": 4, "timing": "real"}, "notes": "y"}
    assert config_diff(a, b) == [("replay.concurrency", 1, 4)]
    assert config_diff(a, a) == []
    # transform name + params are one variable
    c = {"transform": {"name": "identity", "params": {}}}
    d = {"transform": {"name": "truncate_tool_results", "params": {"keep_recent": 4}}}
    assert config_diff(c, d) == [("transform", c["transform"], d["transform"])]


def test_compare_report(tmp_path: Path) -> None:
    a, b = tmp_path / "A", tmp_path / "B"
    for i, hit in enumerate((0.90, 0.91, 0.92)):
        make_run(a, f"r{i}", hit=hit, ttft_p95=500 + i * 10)
        make_run(b, f"r{i}", hit=hit - 0.4, ttft_p95=1500 + i * 10, config={"replay": {"concurrency": 4}})
    md = render_compare("A", load_runs(a), "B", load_runs(b))
    assert "`replay.concurrency`: 1 → 4" in md
    assert "可下结论" in md and "违反" not in md
    # Δ = A − B（实验组 − 对照组），百分比以对照组 B 为分母
    assert "| cache hit rate | 0.9100 ± 0.0100 | 0.5100 ± 0.0100 | 0.4000 (+78.4%) | 40.0× |" in md
    assert "| TTFT P95 | 510 ms ± 10 ms | 1510 ms ± 10 ms | -1000 ms (-66.2%) | 100.0× |" in md

    # identical reruns → std is float-rounding noise, must read as ∞ not 1e15×
    z, w = tmp_path / "Z", tmp_path / "W"
    for i in range(3):
        make_run(z, f"r{i}", hit=0.9633052413981951, ttft_p95=500)
        make_run(w, f"r{i}", hit=0.10586718485761745, ttft_p95=500, config={"replay": {"concurrency": 4}})
    md = render_compare("Z", load_runs(z), "W", load_runs(w))
    assert "| cache hit rate | 0.9633 ± 0.0000 | 0.1059 ± 0.0000 | 0.8574 (+809.9%) | ∞（零噪声） |" in md
    assert "| TTFT P95 | 500 ms ± 0 ms | 500 ms ± 0 ms | 0 ms (+0.0%) | — |" in md

    # two variables → invalid
    c = tmp_path / "C"
    make_run(c, "r0", hit=0.5, ttft_p95=1, config={"replay": {"concurrency": 4, "timing": "compressed"}})
    md = render_compare("A", load_runs(a), "C", load_runs(c))
    assert "动了 2 个变量" in md and "多于一个变量" in md and "不足 3 次" in md

    # fingerprint mismatch → refused
    d = tmp_path / "D"
    make_run(d, "r0", hit=0.5, ttft_p95=1, gpu="RTX 5090")
    md = render_compare("A", load_runs(a), "D", load_runs(d))
    assert "两组指纹不一致" in md and "指纹不一致" in md.split("**判定**")[1]

    assert "没有完成的 run" in render_compare("A", load_runs(a), "E", [])

    # censored tail on one side → that cell and Δ carry a one-sided bound
    t = tmp_path / "T"
    for i in range(3):
        make_run(
            t, f"r{i}", hit=0.5, ttft_p95=500, errors=1, timeouts=1, config={"replay": {"concurrency": 8}}
        )
    md = render_compare("T", load_runs(t), "A", load_runs(a))
    assert "| latency P99 | ≥ 600000 ms ± 0 ms | 4000 ms ± 0 ms | ≥ 596000 ms (+14900.0%) |" in md
    assert "| timeouts (censored) | 1 | — | — | — |" in md
    assert "两侧都是下界时 Δ 不定" in md
    md = render_compare("A", load_runs(a), "T", load_runs(t))
    assert "| latency P99 | 4000 ms ± 0 ms | ≥ 600000 ms ± 0 ms | ≤ -596000 ms (-99.3%) |" in md


def test_main_writes_files(tmp_path: Path) -> None:
    exps = tmp_path / "experiments"
    for i in range(3):
        make_run(exps / "A", f"r{i}", hit=0.9, ttft_p95=500)
        make_run(exps / "B", f"r{i}", hit=0.6, ttft_p95=900, config={"transform": {"name": "rewrite"}})
    assert main(["A", "--experiments-dir", str(exps)]) == 0
    assert (exps / "A" / "report.md").read_text().startswith("# A · 方差")
    assert main(["A", "--against", "B", "--experiments-dir", str(exps)]) == 0
    md = (exps / "A" / "compare-B.md").read_text()
    assert '`transform`: {"name": "identity"} → {"name": "rewrite"}' in md
    assert main(["Z", "--experiments-dir", str(exps)]) == 2
    assert main(["A", "--against", "Z", "--experiments-dir", str(exps)]) == 2
    assert main(["A", "--experiments-dir", str(exps), "--stdout"]) == 0
