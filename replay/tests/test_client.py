import json

import httpx
import pytest

from replay.client import ChatClient
from replay.tests.fake_server import FakeSGLang


@pytest.mark.asyncio
async def test_stream_timing_and_usage() -> None:
    fake = FakeSGLang()
    c = ChatClient("http://fake/v1", "k", 10.0, transport=fake.transport())
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "max_tokens": 4,
        "ignore_eos": True,
    }
    r = await c.send(body)
    assert r.error is None and r.status == 200
    assert (
        r.ttfb_ms is not None
        and r.t_first_delta_ms is not None
        and r.ttft_ms is not None
        and r.latency_ms is not None
    )
    assert r.ttfb_ms <= r.t_first_delta_ms <= r.ttft_ms <= r.latency_ms
    assert r.n_chunks == 1 + 4 + 1  # reasoning + 4 content + usage
    assert r.completion_tokens == 4 and r.prompt_tokens is not None and r.cached_tokens == 0
    assert (
        r.finish_reason == "length" and r.response_id == "chatcmpl-1" and r.request_id_header == "chatcmpl-1"
    )
    assert r.raw_usage is not None and r.raw_usage["prompt_tokens_details"]["cached_tokens"] == 0
    assert fake.requests[0]["messages"] == body["messages"]
    assert (await c.models()) == ["Qwen/Qwen3-8B-FP8"]
    await c.aclose()


@pytest.mark.asyncio
async def test_prefix_reuse_reports_cached_tokens() -> None:
    fake = FakeSGLang()
    c = ChatClient("http://fake/v1", "k", 10.0, transport=fake.transport())
    m1 = [{"role": "system", "content": "s" * 400}, {"role": "user", "content": "a"}]
    m2 = [*m1, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    r1 = await c.send({"messages": m1, "stream": True, "max_tokens": 1, "ignore_eos": True})
    r2 = await c.send({"messages": m2, "stream": True, "max_tokens": 1, "ignore_eos": True})
    assert r1.cached_tokens == 0
    assert r2.cached_tokens is not None and r2.prompt_tokens is not None
    assert 0.8 < r2.cached_tokens / r2.prompt_tokens < 1.0
    await c.aclose()


@pytest.mark.asyncio
async def test_non_stream() -> None:
    fake = FakeSGLang()
    c = ChatClient("http://fake/v1", "k", 10.0, transport=fake.transport())
    r = await c.send({"messages": [{"role": "user", "content": "hi"}], "stream": False, "max_tokens": 2})
    assert r.error is None and r.ttft_ms == r.latency_ms and r.completion_tokens == 3
    await c.aclose()


@pytest.mark.asyncio
async def test_http_error_and_transport_error_become_results() -> None:
    fake = FakeSGLang(fail_every=1)
    c = ChatClient("http://fake/v1", "k", 10.0, transport=fake.transport())
    r = await c.send({"messages": [], "stream": True, "max_tokens": 1})
    assert (
        r.status == 500
        and r.error is not None
        and r.error.startswith("HTTP 500")
        and r.latency_ms is not None
    )
    await c.aclose()

    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    c = ChatClient("http://fake/v1", "k", 10.0, transport=httpx.MockTransport(boom))
    r = await c.send({"messages": [], "stream": True})
    assert r.error == "ConnectError: refused" and r.status is None
    await c.aclose()


@pytest.mark.asyncio
async def test_tolerates_malformed_chunks_and_missing_usage() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        sse = (
            b'data: not json\n\ndata: {"choices":[{"delta":{"content":"x"}}]}\n\n'
            b": comment\n\ndata: [DONE]\n\n"
        )
        return httpx.Response(200, content=sse)

    c = ChatClient("http://fake/v1", "k", 10.0, transport=httpx.MockTransport(handler))
    r = await c.send({"messages": [], "stream": True})
    assert r.error is None and r.n_chunks == 1 and r.ttft_ms is not None
    assert r.prompt_tokens is None and r.cached_tokens is None and r.raw_usage is None
    await c.aclose()


def test_fake_server_serializes_request() -> None:
    fake = FakeSGLang()
    req = httpx.Request(
        "POST", "http://fake/v1/chat/completions", content=json.dumps({"messages": [], "stream": False})
    )
    assert fake.handle(req).status_code == 200
