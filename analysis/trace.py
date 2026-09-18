"""Loader for trace files written by ``extension/`` (schema in ``extension/src/schema.ts``).

A trace is one JSONL file per pi session. This module parses it, validates the
invariants the rest of ``analysis/`` relies on, and exposes typed views. It
never modifies a trace on disk (CLAUDE.md §8.2: traces are read-only).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

SUPPORTED_SCHEMA = 1
"""Trace schema versions this loader understands. Bump together with schema.ts."""

RECORDING_API = "openai-completions"
"""Per docs/decisions.md (2026-09-18) recordings must come from an OpenAI-compatible provider."""

RECORDING_CONTEXT_WINDOW = 65536
"""Per docs/decisions.md (2026-09-18) the recording model's contextWindow is overridden to the
replay-side ``--context-length`` so compaction triggers at the same point. Must match scripts/serve.sh."""


class TraceError(ValueError):
    """A trace file violates an invariant the analysis depends on."""


# ── record types (subset of schema.ts we read; unknown keys are kept in the dicts) ──


class ModelInfo(TypedDict):
    provider: str
    id: str
    api: str
    base_url: str
    context_window: int
    max_tokens: int
    reasoning: bool


class Usage(TypedDict):
    input: int
    output: int
    cacheRead: int
    cacheWrite: int
    totalTokens: int
    cacheWrite1h: NotRequired[int]
    reasoning: NotRequired[int]


class HeaderRecord(TypedDict):
    type: Literal["header"]
    t: int
    seq: int
    schema: int
    session_id: str
    session_file: str | None
    session_reason: str
    cwd: str
    hostname: str
    platform: str
    pi_version: str
    extension_version: str
    extension_git_commit: str | None
    model: ModelInfo | None
    thinking_level: str | None


class ToolCallDigest(TypedDict):
    id: str
    name: str
    args_chars: int


class RequestOutput(TypedDict):
    content: list[Any]
    text_chars: int
    thinking_chars: int
    tool_calls: list[ToolCallDigest]


class RequestRecord(TypedDict):
    type: Literal["request"]
    t: int
    seq: int
    run: int
    turn: int
    req: int
    model: ModelInfo | None
    thinking_level: str | None
    t_request: int
    t_response: int | None
    t_first_delta: int | None
    t_first_content: int | None
    t_end: int | None
    http_status: int | None
    first_delta_type: str | None
    n_deltas: int
    outcome: str
    stop_reason: str | None
    usage: Usage | None
    output: RequestOutput | None
    payload_sha256: str | None
    payload_chars: int | None
    payload: Any


class ToolRecord(TypedDict):
    type: Literal["tool"]
    t: int
    seq: int
    run: int
    turn: int
    tool_call_id: str
    name: str
    t_start: int
    t_end: int | None
    args: Any
    args_chars: int
    result_chars: int | None
    is_error: bool | None


class MessageDigest(TypedDict):
    i: int
    role: str
    sha256: str
    chars: int
    kinds: list[str]


class ContextRecord(TypedDict):
    type: Literal["context"]
    t: int
    seq: int
    run: int
    turn: int
    n_messages: int
    total_chars: int
    messages: list[MessageDigest]


class TurnStartRecord(TypedDict):
    type: Literal["turn_start"]
    t: int
    seq: int
    run: int
    turn: int


class TurnEndRecord(TypedDict):
    type: Literal["turn_end"]
    t: int
    seq: int
    run: int
    turn: int
    stop_reason: str | None
    n_tool_results: int


@dataclass(frozen=True)
class Turn:
    """One agent turn: one LLM request plus the tool calls it triggered."""

    run: int
    turn: int
    start: TurnStartRecord
    end: TurnEndRecord | None
    context: ContextRecord | None
    requests: list[RequestRecord] = field(default_factory=list)
    tools: list[ToolRecord] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, int]:
        return (self.run, self.turn)


@dataclass
class Trace:
    path: Path
    header: HeaderRecord
    records: list[dict[str, Any]]

    # ── typed views ────────────────────────────────────────────────────────

    def of_type(self, type_: str) -> Iterator[dict[str, Any]]:
        return (r for r in self.records if r["type"] == type_)

    @property
    def requests(self) -> list[RequestRecord]:
        return [r for r in self.of_type("request")]  # type: ignore[misc]

    @property
    def tools(self) -> list[ToolRecord]:
        return [r for r in self.of_type("tool")]  # type: ignore[misc]

    @property
    def contexts(self) -> list[ContextRecord]:
        return [r for r in self.of_type("context")]  # type: ignore[misc]

    @property
    def shutdown(self) -> dict[str, Any] | None:
        return next(iter(self.of_type("shutdown")), None)

    @property
    def n_runs(self) -> int:
        return sum(1 for _ in self.of_type("agent_start"))

    @property
    def n_compactions(self) -> int:
        return sum(1 for _ in self.of_type("compaction"))

    @property
    def wall_ms(self) -> int:
        """First record to last record. Includes human think time between runs."""
        return int(self.records[-1]["t"]) - int(self.records[0]["t"])

    @property
    def api(self) -> str | None:
        model = self.header.get("model")
        return model["api"] if model else None

    @property
    def context_window(self) -> int | None:
        model = self.header.get("model")
        return int(model["context_window"]) if model else None

    def turns(self) -> list[Turn]:
        """Group records into turns by (run, turn), in file order."""
        starts: dict[tuple[int, int], TurnStartRecord] = {}
        ends: dict[tuple[int, int], TurnEndRecord] = {}
        contexts: dict[tuple[int, int], ContextRecord] = {}
        reqs: dict[tuple[int, int], list[RequestRecord]] = {}
        tools: dict[tuple[int, int], list[ToolRecord]] = {}
        order: list[tuple[int, int]] = []
        for r in self.records:
            t = r["type"]
            if t not in {"turn_start", "turn_end", "context", "request", "tool"}:
                continue
            key = (int(r["run"]), int(r["turn"]))
            if t == "turn_start":
                starts[key] = r  # type: ignore[assignment]
                order.append(key)
            elif t == "turn_end":
                ends[key] = r  # type: ignore[assignment]
            elif t == "context":
                contexts[key] = r  # type: ignore[assignment]
            elif t == "request":
                reqs.setdefault(key, []).append(r)  # type: ignore[arg-type]
            elif t == "tool":
                tools.setdefault(key, []).append(r)  # type: ignore[arg-type]
        return [
            Turn(
                run=k[0],
                turn=k[1],
                start=starts[k],
                end=ends.get(k),
                context=contexts.get(k),
                requests=reqs.get(k, []),
                tools=tools.get(k, []),
            )
            for k in order
        ]


# ── loading ───────────────────────────────────────────────────────────────


def load_trace(path: Path) -> Trace:
    """Parse and validate one trace file. Raises ``TraceError`` on invariant violations."""
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise TraceError(f"{path}:{lineno}: invalid JSON: {e}") from e
            if not isinstance(rec, dict) or "type" not in rec:
                raise TraceError(f"{path}:{lineno}: record without 'type'")
            records.append(rec)

    if not records:
        raise TraceError(f"{path}: empty trace")
    header = records[0]
    if header["type"] != "header":
        raise TraceError(f"{path}: first record is {header['type']!r}, expected 'header'")
    if header.get("schema") != SUPPORTED_SCHEMA:
        raise TraceError(f"{path}: schema {header.get('schema')!r} unsupported (want {SUPPORTED_SCHEMA})")
    for i, rec in enumerate(records):
        if rec.get("seq") != i:
            raise TraceError(f"{path}: record {i} has seq={rec.get('seq')!r}, expected {i}")
    return Trace(path=path, header=header, records=records)  # type: ignore[arg-type]


def iter_trace_paths(root: Path) -> list[Path]:
    """All ``*.jsonl`` under ``root`` (a file is returned as-is), sorted by name."""
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*.jsonl") if p.is_file())


def prompt_tokens(usage: Usage | None) -> int | None:
    """Total prompt tokens as the provider saw them.

    pi splits OpenAI's ``prompt_tokens`` into ``input`` (uncached) and
    ``cacheRead`` (``prompt_tokens_details.cached_tokens``); the whole prompt
    is their sum.
    """
    if usage is None:
        return None
    return int(usage["input"]) + int(usage["cacheRead"])
