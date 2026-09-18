"""SGLang Prometheus metrics: one-shot snapshots and a background sampler.

Scrape failures are recorded as samples with ``error`` set and never stop a run
(CLAUDE.md §10). The parser is deliberately minimal — the exposition format is
simple and we don't want a client library dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

_LINE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>\S+)")
_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class Sample:
    name: str
    labels: dict[str, str]
    value: float


def parse_prometheus(text: str) -> list[Sample]:
    out: list[Sample] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        try:
            value = float(m.group("value"))
        except ValueError:
            continue
        labels = {k: v.encode().decode("unicode_escape") for k, v in _LABEL.findall(m.group("labels") or "")}
        out.append(Sample(m.group("name"), labels, value))
    return out


def flatten(samples: list[Sample], prefix: str = "sglang:") -> dict[str, float]:
    """``name{k=v,...}`` → value for metrics starting with ``prefix``; labels sorted so keys are stable."""
    flat: dict[str, float] = {}
    for s in samples:
        if not s.name.startswith(prefix):
            continue
        if s.labels:
            key = s.name + "{" + ",".join(f"{k}={v}" for k, v in sorted(s.labels.items())) + "}"
        else:
            key = s.name
        flat[key] = s.value
    return flat


async def snapshot(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """{"t": epoch, "metrics": {...}} or {"t": epoch, "error": "..."}."""
    t = time.time()
    try:
        r = await client.get(url)
        r.raise_for_status()
        return {"t": t, "metrics": flatten(parse_prometheus(r.text))}
    except (httpx.HTTPError, OSError) as e:
        return {"t": t, "error": f"{type(e).__name__}: {e}"}


@dataclass
class Sampler:
    """Append a snapshot to ``path`` every ``interval_s`` until stopped."""

    client: httpx.AsyncClient
    url: str
    path: Path
    interval_s: float = 1.0
    n_ok: int = 0
    n_err: int = 0
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    async def _loop(self) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            while True:
                snap = await snapshot(self.client, self.url)
                if "error" in snap:
                    self.n_err += 1
                else:
                    self.n_ok += 1
                f.write(json.dumps(snap) + "\n")
                f.flush()
                await asyncio.sleep(self.interval_s)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None


# Metrics worth pulling out of a snapshot for the summary (names as of sglang 0.5.x;
# missing ones are reported as null rather than guessed).
KEY_METRICS = (
    "sglang:cache_hit_rate",
    "sglang:num_running_reqs",
    "sglang:num_queue_reqs",
    "sglang:num_used_tokens",
    "sglang:token_usage",
    "sglang:gen_throughput",
    "sglang:prompt_tokens_total",
    "sglang:generation_tokens_total",
    "sglang:num_requests_total",
)


def key_metrics(flat: dict[str, float]) -> dict[str, float | None]:
    """Pick KEY_METRICS regardless of labels (first match wins; SGLang labels by model_name)."""
    out: dict[str, float | None] = {}
    for name in KEY_METRICS:
        hit = next((v for k, v in flat.items() if k == name or k.startswith(name + "{")), None)
        out[name] = hit
    return out
