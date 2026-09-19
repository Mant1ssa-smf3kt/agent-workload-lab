"""Replay scheduling: N trajectories in flight, requests within a trajectory sequential.

``timing=real`` sleeps the recorded gap (scaled, capped) before each request — this is
where tool time and human think time re-enter the load. ``timing=compressed`` sends the
next request the moment the previous one ends.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from replay.client import RequestResult
from replay.config import Config
from replay.trajectory import Step, Trajectory


class Sender(Protocol):
    async def send(self, body: dict[str, Any]) -> RequestResult: ...


@dataclass
class StepResult:
    trajectory: str
    idx: int
    kind: str
    run: int
    turn: int
    req: int | None
    synthetic: bool
    warmup: bool
    gap_planned_ms: int
    gap_actual_ms: float
    t_offset_ms: float
    """Send time relative to run start."""
    recorded: dict[str, Any]
    result: RequestResult

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("result", "recorded")}
        d["recorded"] = self.recorded
        d.update({f"res_{k}": v for k, v in self.result.to_dict().items()})
        return d


@dataclass
class RunStats:
    started_epoch: float
    finished_epoch: float | None = None
    results: list[StepResult] = field(default_factory=list)


def planned_gap_ms(step: Step, cfg: Config) -> int:
    r = cfg.replay
    if r.timing == "compressed" or step.idx == 0:
        return 0
    return int(min(step.gap_before_ms * r.gap_scale, r.max_gap_s * 1000))


async def _replay_one(
    traj: Trajectory,
    cfg: Config,
    sender: Sender,
    run_t0: float,
    warmup_steps: int,
    on_result: Callable[[StepResult], Awaitable[None]] | None,
) -> list[StepResult]:
    out: list[StepResult] = []
    prev_end: float | None = None
    for step in traj.steps:
        gap = planned_gap_ms(step, cfg)
        if gap > 0 and prev_end is not None:
            # Sleep relative to the previous step's end, so a slow server does not
            # stretch the gap on top of its own latency.
            due = prev_end + gap / 1000.0
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
        t_send = time.perf_counter()
        gap_actual = 0.0 if prev_end is None else (t_send - prev_end) * 1000.0
        res = await sender.send(step.payload)
        prev_end = time.perf_counter()
        warm = step.idx < warmup_steps
        sr = StepResult(
            trajectory=traj.id,
            idx=step.idx,
            kind=step.kind,
            run=step.run,
            turn=step.turn,
            req=step.req,
            synthetic=step.synthetic,
            warmup=warm,
            gap_planned_ms=gap,
            gap_actual_ms=gap_actual,
            t_offset_ms=(t_send - run_t0) * 1000.0,
            recorded=step.recorded.__dict__,
            result=res,
        )
        out.append(sr)
        if on_result is not None:
            await on_result(sr)
    return out


async def run_replay(
    trajectories: list[Trajectory],
    cfg: Config,
    sender: Sender,
    on_result: Callable[[StepResult], Awaitable[None]] | None = None,
) -> RunStats:
    """Dispatch trajectories in order with ``concurrency`` workers. Returns all step results in
    completion order (each trajectory's own results are in step order)."""
    stats = RunStats(started_epoch=time.time())
    run_t0 = time.perf_counter()
    queue: asyncio.Queue[Trajectory] = asyncio.Queue()
    for t in trajectories:
        queue.put_nowait(t)
    first_id = trajectories[0].id if trajectories else None
    lock = asyncio.Lock()

    async def worker() -> None:
        while True:
            try:
                traj = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            warm = cfg.replay.warmup_requests if traj.id == first_id else 0
            res = await _replay_one(traj, cfg, sender, run_t0, warm, on_result)
            async with lock:
                stats.results.extend(res)

    n = min(cfg.replay.concurrency, max(1, len(trajectories)))
    await asyncio.gather(*(worker() for _ in range(n)))
    stats.finished_epoch = time.time()
    return stats
