"""An httpx.MockTransport handler that behaves like SGLang's OpenAI-compatible endpoint.

Streams N content chunks (N = max_tokens, or 3 if ignore_eos is false), then a usage
chunk with ``prompt_tokens_details.cached_tokens``. Cached tokens are computed from a
toy radix cache: the longest common prefix (in characters / CHARS_PER_TOKEN) between this
request's serialized messages and any previous request's.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

CHARS_PER_TOKEN = 4


class FakeSGLang:
    def __init__(self, model: str = "Qwen/Qwen3-8B-FP8", fail_every: int = 0) -> None:
        self.model = model
        self.requests: list[dict[str, Any]] = []
        self.seen: list[str] = []
        self.fail_every = fail_every
        self.metrics_calls = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _cached_tokens(self, serialized: str) -> int:
        best = 0
        for prev in self.seen:
            n = 0
            for a, b in zip(prev, serialized, strict=False):
                if a != b:
                    break
                n += 1
            best = max(best, n)
        return best // CHARS_PER_TOKEN

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": self.model}]})
        if path.endswith("/metrics"):
            self.metrics_calls += 1
            text = (
                "# HELP sglang:cache_hit_rate x\n"
                f'sglang:cache_hit_rate{{model_name="{self.model}"}} 0.5\n'
                f'sglang:num_running_reqs{{model_name="{self.model}"}} {len(self.requests) % 3}\n'
                f'sglang:prompt_tokens_total{{model_name="{self.model}"}} {len(self.requests) * 100}\n'
            )
            return httpx.Response(200, text=text)
        if not path.endswith("/chat/completions"):
            return httpx.Response(404, text="not found")

        body = json.loads(request.content)
        self.requests.append(body)
        if self.fail_every and len(self.requests) % self.fail_every == 0:
            return httpx.Response(500, text="boom")
        serialized = json.dumps(body["messages"], ensure_ascii=False)
        prompt_tokens = max(1, len(serialized) // CHARS_PER_TOKEN)
        cached = min(prompt_tokens, self._cached_tokens(serialized))
        self.seen.append(serialized)
        n_out = body.get("max_tokens", 3) if body.get("ignore_eos") else 3
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": n_out,
            "total_tokens": prompt_tokens + n_out,
            "prompt_tokens_details": {"cached_tokens": cached},
        }
        rid = f"chatcmpl-{len(self.requests)}"
        if not body.get("stream"):
            return httpx.Response(
                200,
                json={
                    "id": rid,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "x" * n_out},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": usage,
                },
            )

        def sse() -> bytes:
            out = []
            out.append(
                json.dumps(
                    {
                        "id": rid,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "reasoning_content": "hmm"},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
            )
            for i in range(n_out):
                fr = "length" if i == n_out - 1 else None
                out.append(
                    json.dumps(
                        {"id": rid, "choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": fr}]}
                    )
                )
            out.append(json.dumps({"id": rid, "choices": [], "usage": usage}))
            return "".join(f"data: {o}\n\n" for o in out).encode() + b"data: [DONE]\n\n"

        return httpx.Response(
            200, content=sse(), headers={"content-type": "text/event-stream", "x-request-id": rid}
        )
