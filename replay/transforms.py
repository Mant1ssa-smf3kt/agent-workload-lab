"""W3: context-assembly strategies applied to a trajectory's request payloads before replay.

Each transform rewrites what the harness would have sent, request by request, the way a
real harness feature does — so the replayed sequence has the same *content* the model
would need but a different byte-level prefix history. ``identity`` is the append-only
control (what pi actually sent). Everything else is a candidate "looks harmless" rewrite.

Transforms are pure: they return new Step objects with new payload dicts and never mutate
their input. Parameters come from ``transform.params`` in the experiment config.
"""

from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from replay.trajectory import Step

Transform = Callable[[list[Step], dict[str, Any]], list[Step]]


def _with_payload(step: Step, payload: dict[str, Any]) -> Step:
    return replace(step, payload=payload)


def _messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    msgs = payload.get("messages")
    return list(msgs) if isinstance(msgs, list) else []


# ── identity ──────────────────────────────────────────────────────────────


def identity(steps: list[Step], params: dict[str, Any]) -> list[Step]:
    return list(steps)


# ── system_timestamp ──────────────────────────────────────────────────────


def system_timestamp(steps: list[Step], params: dict[str, Any]) -> list[Step]:
    """Put the "current time" into the system prompt of every request, as harnesses that
    stamp the date/time or session clock into their system prompt do.

    The clock is deterministic (``base_epoch`` + ``idx`` × ``step_s``) so repeated runs send
    identical bytes; what matters for the cache is that every request differs.

    params: ``position`` = "end" (default; after the system text, before the template renders
    tools) | "start"; ``template`` with ``{ts}``; ``base_epoch``; ``step_s``.
    """
    position = params.get("position", "end")
    template = params.get("template", "\n\nCurrent time: {ts}")
    base = int(params.get("base_epoch", 1_700_000_000))
    step_s = int(params.get("step_s", 60))
    out: list[Step] = []
    for s in steps:
        ts = dt.datetime.fromtimestamp(base + s.idx * step_s, tz=dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        stamp = template.format(ts=ts)
        payload = copy.deepcopy(s.payload)
        msgs = _messages(payload)
        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        if sys_i is None:
            msgs.insert(0, {"role": "system", "content": stamp.strip()})
        else:
            content = msgs[sys_i].get("content")
            if isinstance(content, str):
                msgs[sys_i]["content"] = (
                    (stamp.lstrip() + "\n\n" + content) if position == "start" else (content + stamp)
                )
            elif isinstance(content, list):
                block = {"type": "text", "text": stamp.strip()}
                msgs[sys_i]["content"] = [block, *content] if position == "start" else [*content, block]
        payload["messages"] = msgs
        out.append(_with_payload(s, payload))
    return out


# ── tools_rotate ──────────────────────────────────────────────────────────


def tools_rotate(steps: list[Step], params: dict[str, Any]) -> list[Step]:
    """Rotate the ``tools`` list by one position every ``every`` requests. Same tool set,
    same semantics; only the order the template renders them in changes — which is what an
    unordered tool registry or dynamic tool loading does to the prompt prefix.
    """
    every = max(1, int(params.get("every", 1)))
    out: list[Step] = []
    for s in steps:
        payload = copy.deepcopy(s.payload)
        tools = payload.get("tools")
        if isinstance(tools, list) and len(tools) > 1:
            k = (s.idx // every) % len(tools)
            payload["tools"] = tools[k:] + tools[:k]
        out.append(_with_payload(s, payload))
    return out


# ── truncate_tool_results ─────────────────────────────────────────────────


def truncate_tool_results(steps: list[Step], params: dict[str, Any]) -> list[Step]:
    """Keep the most recent ``keep_recent`` tool results intact and truncate every older one to
    ``max_chars`` — the classic "context management" optimization. Because the window slides,
    each request rewrites the tool result that just aged out, so the shared prefix ends there.
    """
    keep_recent = max(0, int(params.get("keep_recent", 4)))
    max_chars = max(0, int(params.get("max_chars", 800)))
    marker = str(params.get("marker", "\n…[truncated by harness]"))
    out: list[Step] = []
    for s in steps:
        payload = copy.deepcopy(s.payload)
        msgs = _messages(payload)
        tool_idx = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
        for i in tool_idx[: max(0, len(tool_idx) - keep_recent)]:
            content = msgs[i].get("content")
            if isinstance(content, str) and len(content) > max_chars:
                msgs[i]["content"] = content[:max_chars] + marker
            elif isinstance(content, list):
                # OpenAI-style content blocks: truncate the first text block, drop the rest.
                text = next(
                    (b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text"), ""
                )
                if isinstance(text, str) and len(text) > max_chars:
                    msgs[i]["content"] = text[:max_chars] + marker
        payload["messages"] = msgs
        out.append(_with_payload(s, payload))
    return out


# ── registry ──────────────────────────────────────────────────────────────

TRANSFORMS: dict[str, Transform] = {
    "identity": identity,
    "system_timestamp": system_timestamp,
    "tools_rotate": tools_rotate,
    "truncate_tool_results": truncate_tool_results,
}


def apply_transform(name: str, params: dict[str, Any], steps: list[Step]) -> list[Step]:
    try:
        fn = TRANSFORMS[name]
    except KeyError:
        raise ValueError(f"unknown transform {name!r}; known: {sorted(TRANSFORMS)}") from None
    return fn(steps, params)
