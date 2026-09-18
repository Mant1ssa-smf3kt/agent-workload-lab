"""Synthetic trace builder mirroring the record shapes extension/ writes (schema v1).

Field names and event order follow what `extension/smoke/run.sh` observes from
real pi 0.85.1; keep them in sync if the schema changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

MODEL = {
    "provider": "fake",
    "id": "fake-1",
    "api": "openai-completions",
    "base_url": "http://127.0.0.1:18080/v1",
    "context_window": 65536,
    "max_tokens": 1024,
    "reasoning": False,
}

TOOLS = [
    {"type": "function", "function": {"name": n, "parameters": {}}} for n in ("read", "bash", "edit", "write")
]


class TraceBuilder:
    """Emit records with a monotonic clock; `t` advances by explicit `dt` per call."""

    def __init__(self, t0: int = 1_700_000_000_000, model: dict[str, Any] | None = None) -> None:
        self.t = t0
        self.seq = 0
        self.records: list[dict[str, Any]] = []
        self.model = MODEL if model is None else model
        self.req = -1

    def tick(self, dt: int) -> int:
        self.t += dt
        return self.t

    def emit(self, rec: dict[str, Any], dt: int = 0) -> dict[str, Any]:
        self.tick(dt)
        full = {**rec, "t": rec.get("t", self.t), "seq": self.seq}
        self.seq += 1
        self.records.append(full)
        return full

    # ── framing ────────────────────────────────────────────────────────────

    def header(self, session_id: str = "sess-1", **over: Any) -> None:
        self.emit(
            {
                "type": "header",
                "schema": 1,
                "session_id": session_id,
                "session_file": None,
                "session_reason": "startup",
                "previous_session_file": None,
                "cwd": "/work/repo",
                "hostname": "box",
                "platform": "darwin-arm64",
                "node_version": "v26.4.0",
                "pi_version": "0.85.1",
                "extension_version": "0.1.0",
                "extension_git_commit": "abc123",
                "model": self.model,
                "thinking_level": "off",
                "trace_dir_source": "flag",
                **over,
            }
        )

    def user_prompt(self, run: int, prompt: str, dt: int = 0) -> None:
        self.emit(
            {
                "type": "user_prompt",
                "run": run,
                "prompt": prompt,
                "prompt_chars": len(prompt),
                "n_images": 0,
                "system_prompt_sha256": "s" * 64,
                "system_prompt_chars": 100,
            },
            dt,
        )

    def agent_start(self, run: int, dt: int = 1) -> None:
        self.emit({"type": "agent_start", "run": run}, dt)

    def agent_end(self, run: int, n_messages: int, dt: int = 1) -> None:
        self.emit({"type": "agent_end", "run": run, "n_messages": n_messages}, dt)
        self.emit({"type": "agent_settled", "run": run})

    def turn_start(self, run: int, turn: int, dt: int = 0) -> None:
        self.emit({"type": "turn_start", "run": run, "turn": turn, "pi_timestamp": self.t + dt}, dt)

    def turn_end(self, run: int, turn: int, stop: str, n_tool_results: int, dt: int = 1) -> None:
        self.emit(
            {
                "type": "turn_end",
                "run": run,
                "turn": turn,
                "stop_reason": stop,
                "n_tool_results": n_tool_results,
            },
            dt,
        )

    def context(self, run: int, turn: int, messages: list[dict[str, Any]], dt: int = 0) -> None:
        digests = [
            {
                "i": i,
                "role": m["role"],
                "sha256": f"{hash(json.dumps(m, sort_keys=True)) & 0xFFFFFFFF:08x}",
                "chars": len(json.dumps(m)),
                "kinds": ["text"],
            }
            for i, m in enumerate(messages)
        ]
        self.emit(
            {
                "type": "context",
                "run": run,
                "turn": turn,
                "n_messages": len(digests),
                "total_chars": sum(d["chars"] for d in digests),
                "messages": digests,
            },
            dt,
        )

    def request(
        self,
        run: int,
        turn: int,
        messages: list[dict[str, Any]],
        *,
        content: list[dict[str, Any]],
        stop: str = "stop",
        outcome: str = "done",
        prompt_tokens: int = 100,
        cached: int = 0,
        output_tokens: int = 10,
        ttfb: int = 50,
        ttft: int = 60,
        model_ms: int = 200,
        pre: int = 5,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.req += 1
        t_req = self.tick(pre)
        payload = {
            "model": self.model["id"],
            "messages": messages,
            "stream": True,
            "tools": TOOLS if tools is None else tools,
        }
        pj = json.dumps(payload)
        tool_calls = [
            {"id": c["id"], "name": c["name"], "args_chars": len(json.dumps(c["arguments"]))}
            for c in content
            if c["type"] == "toolCall"
        ]
        finished = outcome in {"done", "error", "aborted"}
        rec = {
            "type": "request",
            "t": t_req,
            "run": run,
            "turn": turn,
            "req": self.req,
            "model": self.model,
            "thinking_level": "off",
            "t_request": t_req,
            "t_response": t_req + ttfb if finished else None,
            "t_first_delta": t_req + ttft if finished else None,
            "t_first_content": t_req + ttft if finished else None,
            "t_end": t_req + model_ms if finished else None,
            "http_status": 200 if finished else None,
            "response_headers": {"content-type": "text/event-stream"} if finished else None,
            "first_delta_type": "text" if finished else None,
            "n_deltas": 3 if finished else 0,
            "outcome": outcome,
            "stop_reason": stop if finished else None,
            "error_message": None,
            "usage": (
                {
                    "input": prompt_tokens - cached,
                    "output": output_tokens,
                    "cacheRead": cached,
                    "cacheWrite": 0,
                    "totalTokens": prompt_tokens + output_tokens,
                }
                if finished
                else None
            ),
            "output": (
                {
                    "content": content,
                    "text_chars": sum(len(c["text"]) for c in content if c["type"] == "text"),
                    "thinking_chars": 0,
                    "tool_calls": tool_calls,
                }
                if finished
                else None
            ),
            "payload_sha256": "p" * 64,
            "payload_chars": len(pj),
            "payload": payload,
        }
        if finished:
            self.t = t_req + model_ms
        rec_out = self.emit(rec)
        return rec_out

    def tool(
        self,
        run: int,
        turn: int,
        call_id: str,
        name: str,
        args: dict[str, Any],
        *,
        duration: int,
        result_chars: int = 50,
        is_error: bool = False,
        pre: int = 1,
    ) -> None:
        t_start = self.tick(pre)
        self.t = t_start + duration
        self.emit(
            {
                "type": "tool",
                "t": t_start,
                "run": run,
                "turn": turn,
                "tool_call_id": call_id,
                "name": name,
                "t_start": t_start,
                "t_end": t_start + duration,
                "args": args,
                "args_chars": len(json.dumps(args)),
                "result_chars": result_chars,
                "is_error": is_error,
            }
        )

    def compaction(self, run: int, tokens_before: int, dt: int = 1) -> None:
        self.emit(
            {
                "type": "compaction",
                "run": run,
                "reason": "threshold",
                "will_retry": False,
                "from_extension": False,
                "tokens_before": tokens_before,
                "summary_chars": 500,
                "usage": None,
            },
            dt,
        )

    def shutdown(self, n_runs: int, n_requests: int, n_tools: int, dt: int = 1) -> None:
        self.emit(
            {
                "type": "shutdown",
                "reason": "quit",
                "n_runs": n_runs,
                "n_requests": n_requests,
                "n_tools": n_tools,
            },
            dt,
        )

    def write(self, path: Path) -> Path:
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in self.records) + "\n", encoding="utf-8"
        )
        return path


SYS = {"role": "system", "content": "You are pi."}
U0 = {"role": "user", "content": "read the readme"}
A0 = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "bash", "arguments": '{"command":"cat README.md"}'},
        }
    ],
}
T0 = {"role": "tool", "tool_call_id": "call_1", "content": "hello from smoke repo\n"}
A1 = {"role": "assistant", "content": "The README says hello."}
U1 = {"role": "user", "content": "now edit it"}


def build_two_run_trace(session_id: str = "sess-1") -> TraceBuilder:
    """Run 0: tool-call turn + text turn. Run 1 (after 30 s think time): one turn with a
    superseded request (retry), then compaction. Exercises every row type."""
    b = TraceBuilder()
    b.header(session_id=session_id)
    # run 0
    b.user_prompt(0, "read the readme")
    b.agent_start(0)
    b.turn_start(0, 0)
    b.context(0, 0, [U0])
    b.request(
        0,
        0,
        [SYS, U0],
        content=[
            {"type": "toolCall", "id": "call_1", "name": "bash", "arguments": {"command": "cat README.md"}}
        ],
        stop="toolUse",
        prompt_tokens=100,
        cached=0,
        output_tokens=12,
        ttfb=50,
        ttft=60,
        model_ms=200,
        pre=5,
    )
    b.tool(0, 0, "call_1", "bash", {"command": "cat README.md"}, duration=40, pre=2)
    b.turn_end(0, 0, "toolUse", 1, dt=3)
    b.turn_start(0, 1)
    b.context(0, 1, [U0, {"role": "assistant"}, {"role": "toolResult"}])
    b.request(
        0,
        1,
        [SYS, U0, A0, T0],
        content=[{"type": "text", "text": "The README says hello."}],
        stop="stop",
        prompt_tokens=140,
        cached=100,
        output_tokens=8,
        ttfb=45,
        ttft=55,
        model_ms=150,
        pre=4,
    )
    b.turn_end(0, 1, "stop", 0, dt=2)
    b.agent_end(0, 4)
    # think time
    b.user_prompt(1, "now edit it", dt=30_000)
    b.agent_start(1)
    b.turn_start(1, 0)
    b.context(1, 0, [U0, {"role": "assistant"}, {"role": "toolResult"}, {"role": "assistant"}, U1])
    b.request(1, 0, [SYS, U0, A0, T0, A1, U1], content=[], outcome="superseded", prompt_tokens=170, pre=5)
    b.tick(100)  # gap before retry → unaccounted
    b.request(
        1,
        0,
        [SYS, U0, A0, T0, A1, U1],
        content=[{"type": "text", "text": "Done."}],
        stop="stop",
        prompt_tokens=170,
        cached=140,
        output_tokens=3,
        ttfb=40,
        ttft=50,
        model_ms=120,
        pre=5,
    )
    b.turn_end(1, 0, "stop", 0, dt=2)
    b.compaction(1, tokens_before=170)
    b.agent_end(1, 6)
    b.shutdown(2, 4, 1)
    return b


@pytest.fixture
def two_run_trace(tmp_path: Path) -> Path:
    return build_two_run_trace().write(tmp_path / "20260918T100000.000_sess-1.jsonl")


@pytest.fixture
def traces_dir(tmp_path: Path) -> Path:
    d = tmp_path / "traces"
    d.mkdir()
    build_two_run_trace("sess-a").write(d / "a.jsonl")
    build_two_run_trace("sess-b").write(d / "b.jsonl")
    return d
