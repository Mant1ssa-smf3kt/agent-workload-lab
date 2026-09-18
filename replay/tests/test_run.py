import json
from pathlib import Path

import pytest

import replay.run as run_mod
from analysis.tests.conftest import build_two_run_trace
from replay.tests.fake_server import FakeSGLang


def make_experiment(tmp_path: Path, extra: str = "") -> tuple[Path, Path]:
    traces = tmp_path / "traces"
    traces.mkdir()
    build_two_run_trace("a").write(traces / "a.jsonl")
    build_two_run_trace("b").write(traces / "b.jsonl")
    exp = tmp_path / "experiments" / "e1"
    exp.mkdir(parents=True)
    fp = tmp_path / "serve-latest.json"
    fp.write_text(
        json.dumps(
            {"gpu": {"name": "RTX 4090"}, "sglang_version": "0.5.20", "model": {"id": "Qwen/Qwen3-8B-FP8"}}
        )
    )
    cfg = exp / "config.yaml"
    cfg.write_text(
        f"traces:\n  dir: {traces}\nfingerprint: {fp}\n"
        f"replay:\n  timing: compressed\n  concurrency: 2\n"
        f"server:\n  base_url: http://fake/v1\n{extra}"
    )
    return cfg, exp


def test_dry_run_writes_plan_without_network(tmp_path: Path) -> None:
    cfg, exp = make_experiment(tmp_path)
    assert run_mod.main([str(cfg), "--dry-run"]) == 0
    runs = list((exp / "out").iterdir())
    assert len(runs) == 1 and runs[0].name.endswith("-dry")
    plan = json.loads((runs[0] / "plan.json").read_text())
    assert plan["n_trajectories"] == 2 and plan["n_steps"] == 6 and plan["timing"] == "compressed"
    fp = json.loads((runs[0] / "fingerprint.json").read_text())
    assert fp["gpu"] == {"name": "RTX 4090"} and len(fp["traces"]) == 2
    assert (runs[0] / "config.resolved.yaml").exists() and not (runs[0] / "summary.json").exists()


def test_dry_run_without_fingerprint_is_fine_but_real_run_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg, _ = make_experiment(tmp_path)
    cfg.write_text(
        cfg.read_text().replace(
            f"fingerprint: {tmp_path / 'serve-latest.json'}", "fingerprint: /nonexistent.json"
        )
    )
    assert run_mod.main([str(cfg), "--dry-run"]) == 0
    monkeypatch.setattr(run_mod, "_TRANSPORT", FakeSGLang().transport())
    assert run_mod.main([str(cfg)]) == 2


def test_real_run_end_to_end_against_fake_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, _ = make_experiment(tmp_path)
    fake = FakeSGLang()
    monkeypatch.setattr(run_mod, "_TRANSPORT", fake.transport())
    assert run_mod.main([str(cfg), "--out", str(tmp_path / "artifacts")]) == 0
    runs = list((tmp_path / "artifacts").iterdir())
    assert len(runs) == 1 and not runs[0].name.endswith("-dry")
    out = runs[0]
    for name in (
        "config.resolved.yaml",
        "fingerprint.json",
        "plan.json",
        "requests.jsonl",
        "metrics_before.json",
        "metrics_after.json",
        "metrics_samples.jsonl",
        "summary.json",
    ):
        assert (out / name).exists(), name
    s = json.loads((out / "summary.json").read_text())
    assert s["n_errors"] == 0 and s["all"]["n"] == 6 and s["all"]["n_with_usage"] == 6
    assert s["all"]["cache_hit_rate"] is not None and 0 < s["all"]["cache_hit_rate"] < 1
    assert s["metrics_before"]["sglang:cache_hit_rate"] == 0.5
    reqs = [json.loads(line) for line in (out / "requests.jsonl").read_text().splitlines()]
    assert len(reqs) == 6 and all(r["res_error"] is None for r in reqs)
    # the server received normalized bodies: replay model, ignore_eos, recorded max_tokens, no provider extras
    body = fake.requests[0]
    assert (
        body["model"] == "Qwen/Qwen3-8B-FP8"
        and body["ignore_eos"] is True
        and body["max_tokens"] in (12, 8, 3)
    )
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert fake.metrics_calls >= 2


def test_real_run_with_failures_exits_1_but_writes_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg, exp = make_experiment(tmp_path, extra="  metrics_url: null\n")
    monkeypatch.setattr(run_mod, "_TRANSPORT", FakeSGLang(fail_every=3).transport())
    assert run_mod.main([str(cfg)]) == 1
    out = next((exp / "out").iterdir())
    s = json.loads((out / "summary.json").read_text())
    assert s["n_errors"] == 2 and s["all"]["n"] == 4
    assert (
        s["metrics_before"]["sglang:cache_hit_rate"] is None and not (out / "metrics_samples.jsonl").exists()
    )


def test_model_mismatch_and_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg, _ = make_experiment(tmp_path, extra="  model: other-model\n")
    monkeypatch.setattr(run_mod, "_TRANSPORT", FakeSGLang().transport())
    assert run_mod.main([str(cfg)]) == 2
    import httpx

    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    (tmp_path / "b").mkdir()
    cfg, _ = make_experiment(tmp_path / "b")
    monkeypatch.setattr(run_mod, "_TRANSPORT", httpx.MockTransport(down))
    assert run_mod.main([str(cfg)]) == 2


def test_no_trajectories_and_bad_config(tmp_path: Path) -> None:
    exp = tmp_path / "e"
    exp.mkdir()
    (tmp_path / "empty").mkdir()
    cfg = exp / "config.yaml"
    cfg.write_text(f"traces:\n  dir: {tmp_path / 'empty'}\n")
    assert run_mod.main([str(cfg), "--dry-run"]) == 2
    cfg.write_text("replay:\n  concurrency: 0\n")
    assert run_mod.main([str(cfg), "--dry-run"]) == 2
