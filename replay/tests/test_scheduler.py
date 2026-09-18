import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from replay.client import RequestResult
from replay.config import Config, ReplayConfig
from replay.scheduler import planned_gap_ms, run_replay
from replay.trajectory import Recorded, Step, Trajectory

REC = Recorded(None, None, None, None, None, None)


def traj(tid: str, gaps: list[int]) -> Trajectory:
    t = Trajectory(
        id=tid, path=Path(tid), session_id=tid, pi_version="p", extension_version="e", recorded_model=None
    )
    for i, g in enumerate(gaps):
        t.steps.append(Step(tid, i, "request", 0, i, i, g, {"messages": [], "n": i, "t": tid}, REC))
    return t


class FakeSender:
    def __init__(self, delay_s: float = 0.0) -> None:
        self.calls: list[tuple[float, str, int]] = []
        self.delay = delay_s
        self.inflight = 0
        self.max_inflight = 0

    async def send(self, body: dict[str, Any]) -> RequestResult:
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        self.calls.append((time.perf_counter(), body["t"], body["n"]))
        await asyncio.sleep(self.delay)
        self.inflight -= 1
        return RequestResult(
            t_send_epoch=time.time(), latency_ms=self.delay * 1000, prompt_tokens=10, cached_tokens=5
        )


def test_planned_gap() -> None:
    s0 = Step("a", 0, "request", 0, 0, 0, 5000, {}, REC)
    s1 = Step("a", 1, "request", 0, 1, 1, 5000, {}, REC)
    assert planned_gap_ms(s0, Config(name="x")) == 0  # first step never waits
    assert planned_gap_ms(s1, Config(name="x")) == 5000
    assert planned_gap_ms(s1, Config(name="x", replay=ReplayConfig(timing="compressed"))) == 0
    assert planned_gap_ms(s1, Config(name="x", replay=ReplayConfig(gap_scale=0.5))) == 2500
    assert planned_gap_ms(s1, Config(name="x", replay=ReplayConfig(max_gap_s=1))) == 1000


@pytest.mark.asyncio
async def test_compressed_sequential_within_trajectory_and_concurrency_across() -> None:
    cfg = Config(name="x", replay=ReplayConfig(timing="compressed", concurrency=2))
    sender = FakeSender(delay_s=0.01)
    trajs = [traj("a", [0, 100, 100]), traj("b", [0, 100]), traj("c", [0])]
    stats = await run_replay(trajs, cfg, sender)
    assert len(stats.results) == 6 and stats.finished_epoch is not None
    assert sender.max_inflight == 2
    # within a trajectory, steps are strictly ordered
    for tid in "abc":
        assert [n for _, t, n in sender.calls if t == tid] == sorted(
            n for _, t, n in sender.calls if t == tid
        )
    # compressed: no planned gaps
    assert all(r.gap_planned_ms == 0 for r in stats.results)
    assert all(r.gap_actual_ms < 50 for r in stats.results if r.idx > 0)
    # results carry identity + recorded reference
    r = next(r for r in stats.results if r.trajectory == "a" and r.idx == 2)
    assert r.kind == "request" and r.req == 2 and r.result.cached_tokens == 5 and not r.warmup
    assert "res_latency_ms" in r.to_dict() and r.to_dict()["recorded"]["prompt_tokens"] is None


@pytest.mark.asyncio
async def test_real_timing_honours_scaled_gaps() -> None:
    cfg = Config(name="x", replay=ReplayConfig(timing="real", gap_scale=0.1, max_gap_s=0.05))
    sender = FakeSender()
    stats = await run_replay([traj("a", [0, 300, 900])], cfg, sender)  # → 30 ms, then capped 50 ms
    gaps = sorted((r.idx, r.gap_planned_ms, r.gap_actual_ms) for r in stats.results)
    assert [g[1] for g in gaps] == [0, 30, 50]
    assert gaps[1][2] >= 28 and gaps[2][2] >= 48


@pytest.mark.asyncio
async def test_warmup_marks_first_requests() -> None:
    cfg = Config(name="x", replay=ReplayConfig(timing="compressed", warmup_requests=2))
    stats = await run_replay([traj("a", [0, 0, 0])], cfg, FakeSender())
    assert [r.warmup for r in sorted(stats.results, key=lambda r: r.idx)] == [True, True, False]


@pytest.mark.asyncio
async def test_on_result_callback_and_empty_input() -> None:
    seen: list[int] = []

    async def cb(r: Any) -> None:
        seen.append(r.idx)

    cfg = Config(name="x", replay=ReplayConfig(timing="compressed"))
    await run_replay([traj("a", [0, 0])], cfg, FakeSender(), on_result=cb)
    assert seen == [0, 1]
    stats = await run_replay([], cfg, FakeSender())
    assert stats.results == []
