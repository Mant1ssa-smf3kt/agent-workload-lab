"""OpenAI-compatible chat-completions client with the timing points the metrics need.

TTFT here follows CLAUDE.md §5: request send → first *content* token (text or tool-call
delta; reasoning deltas are recorded separately as ``t_first_delta``), including queueing.
Every failure becomes a ``RequestResult`` with ``error`` set — never an exception out of
``send`` (CLAUDE.md §10).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx


@dataclass
class RequestResult:
    t_send_epoch: float
    """Wall clock (s) at send; for joining with metrics samples."""
    ttfb_ms: float | None = None
    """Send → HTTP response headers."""
    t_first_delta_ms: float | None = None
    """Send → first streamed delta of any kind (reasoning included)."""
    ttft_ms: float | None = None
    """Send → first content/tool-call delta."""
    latency_ms: float | None = None
    """Send → stream fully consumed."""
    status: int | None = None
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    """``usage.prompt_tokens_details.cached_tokens`` as the server reported it (SGLang: radix hits)."""
    raw_usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    response_id: str | None = None
    n_chunks: int = 0
    request_id_header: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_usage(res: RequestResult, usage: dict[str, Any]) -> None:
    res.raw_usage = usage
    res.prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
    res.completion_tokens = _int_or_none(usage.get("completion_tokens"))
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if cached is None:
        cached = usage.get("cached_tokens")  # some servers put it top-level
    res.cached_tokens = _int_or_none(cached)


def _int_or_none(v: Any) -> int | None:
    return int(v) if isinstance(v, int | float) else None


def _delta_kind(chunk: dict[str, Any]) -> str | None:
    """'content' | 'reasoning' | None for a streamed chunk."""
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        if delta.get("content") or delta.get("tool_calls"):
            return "content"
        if delta.get("reasoning_content") or delta.get("reasoning"):
            return "reasoning"
    return None


class ChatClient:
    def __init__(
        self, base_url: str, api_key: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def models(self) -> list[str]:
        r = await self._client.get("/models")
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]

    async def send(self, body: dict[str, Any]) -> RequestResult:
        res = RequestResult(t_send_epoch=time.time())
        t0 = time.perf_counter()

        def ms() -> float:
            return (time.perf_counter() - t0) * 1000.0

        try:
            if body.get("stream"):
                async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                    res.status = resp.status_code
                    res.ttfb_ms = ms()
                    res.request_id_header = resp.headers.get("x-request-id")
                    if resp.status_code != 200:
                        text = (await resp.aread()).decode("utf-8", "replace")
                        res.error = f"HTTP {resp.status_code}: {text[:500]}"
                        res.latency_ms = ms()
                        return res
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        res.n_chunks += 1
                        kind = _delta_kind(chunk)
                        if kind is not None and res.t_first_delta_ms is None:
                            res.t_first_delta_ms = ms()
                        if kind == "content" and res.ttft_ms is None:
                            res.ttft_ms = ms()
                        for choice in chunk.get("choices") or []:
                            if choice.get("finish_reason"):
                                res.finish_reason = choice["finish_reason"]
                        if chunk.get("id") and res.response_id is None:
                            res.response_id = chunk["id"]
                        if isinstance(chunk.get("usage"), dict):
                            _extract_usage(res, chunk["usage"])
                    res.latency_ms = ms()
            else:
                resp = await self._client.post("/chat/completions", json=body)
                res.status = resp.status_code
                res.ttfb_ms = ms()
                res.request_id_header = resp.headers.get("x-request-id")
                if resp.status_code != 200:
                    res.error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                    res.latency_ms = ms()
                    return res
                data = resp.json()
                res.latency_ms = ms()
                res.ttft_ms = res.latency_ms
                res.t_first_delta_ms = res.latency_ms
                res.response_id = data.get("id")
                for choice in data.get("choices") or []:
                    res.finish_reason = choice.get("finish_reason")
                if isinstance(data.get("usage"), dict):
                    _extract_usage(res, data["usage"])
        except (httpx.HTTPError, OSError, ValueError) as e:
            res.error = f"{type(e).__name__}: {e}"
            res.latency_ms = ms()
        return res
