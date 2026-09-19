import asyncio
import json
from pathlib import Path

import httpx
import pytest

from metrics.sglang import Sampler, flatten, key_metrics, parse_prometheus, snapshot

TEXT = """# HELP sglang:cache_hit_rate The prefix cache hit rate.
# TYPE sglang:cache_hit_rate gauge
sglang:cache_hit_rate{model_name="Qwen/Qwen3-8B-FP8"} 0.8125
sglang:num_running_reqs{model_name="Qwen/Qwen3-8B-FP8"} 3
sglang:prompt_tokens_total{is_streaming="true",model_name="Qwen/Qwen3-8B-FP8"} 123456.0
sglang:prompt_tokens_total{is_streaming="false",model_name="Qwen/Qwen3-8B-FP8"} 44.0
sglang:e2e_request_latency_seconds_bucket{le="0.5",model_name="Qwen/Qwen3-8B-FP8",name="x\\"y"} 7
python_gc_objects_collected_total{generation="0"} 100
weird line without value
sglang:nan_metric NaN
"""


def test_parse_and_flatten() -> None:
    samples = parse_prometheus(TEXT)
    names = [s.name for s in samples]
    assert "sglang:cache_hit_rate" in names and "python_gc_objects_collected_total" in names
    hist = next(s for s in samples if s.name.endswith("_bucket"))
    assert hist.labels == {"le": "0.5", "model_name": "Qwen/Qwen3-8B-FP8", "name": 'x"y'} and hist.value == 7
    flat = flatten(samples)
    assert flat["sglang:cache_hit_rate{model_name=Qwen/Qwen3-8B-FP8}"] == 0.8125
    assert "python_gc_objects_collected_total{generation=0}" not in flat
    assert any(k.startswith("sglang:nan_metric") for k in flat)  # NaN parses as float
    km = key_metrics(flat)
    assert km["sglang:cache_hit_rate"] == 0.8125 and km["sglang:num_running_reqs"] == 3
    assert km["sglang:prompt_tokens_total"] == 123500.0  # counters summed over label sets
    assert km["sglang:gen_throughput"] is None


@pytest.mark.asyncio
async def test_snapshot_ok_and_error() -> None:
    ok = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=TEXT)))
    snap = await snapshot(ok, "http://s/metrics")
    assert "metrics" in snap and snap["metrics"]["sglang:num_running_reqs{model_name=Qwen/Qwen3-8B-FP8}"] == 3
    bad = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down")))
    snap = await snapshot(bad, "http://s/metrics")
    assert "error" in snap and "503" in snap["error"]

    def raise_(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    snap = await snapshot(httpx.AsyncClient(transport=httpx.MockTransport(raise_)), "http://s/metrics")
    assert snap["error"].startswith("ConnectError")


@pytest.mark.asyncio
async def test_sampler_appends_and_survives_errors(tmp_path: Path) -> None:
    n = {"i": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(200 if n["i"] % 2 else 500, text=TEXT)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    s = Sampler(client, "http://s/metrics", tmp_path / "m.jsonl", interval_s=0.01)
    s.start()
    await asyncio.sleep(0.06)
    await s.stop()
    lines = [json.loads(line) for line in (tmp_path / "m.jsonl").read_text().splitlines()]
    assert len(lines) >= 3 and s.n_ok >= 1 and s.n_err >= 1
    assert any("metrics" in x for x in lines) and any("error" in x for x in lines)
    await s.stop()  # idempotent
