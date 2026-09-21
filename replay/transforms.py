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


TIMESTAMP_POSITIONS = ("end", "start", "after_tools", "tail", "tail_append")


def system_timestamp(steps: list[Step], params: dict[str, Any]) -> list[Step]:
    """Give every request the "current time", the way harnesses that stamp the date/time or a
    session clock into the context do. Same information in every variant; only *where* it lands
    in the rendered prompt differs, which is the whole point (docs/decisions.md 2026-09-19/21).

    The clock is deterministic (``base_epoch`` + ``idx`` × ``step_s``) so repeated runs send
    identical bytes; what matters for the cache is that every request differs.

    params: ``position`` =
      "end" (default): appended to the system text — before the template renders tools, so the
        tools block and the whole message history re-prefill every turn (W3 headline);
      "start": in front of the system text;
      "after_tools": a second ``system`` message right after the first, i.e. rendered after the
        tools block; the history still re-prefills;
      "tail": one ``user`` message at the very end, replaced every request (an ephemeral
        reminder); everything before it stays byte-identical to the previous request;
      "tail_append": the stamp of every earlier request stays in the history at the spot it was
        sent (a persisted reminder) and this request's own goes at the end — literally
        append-only, at the price of the prompt growing by one stamp per turn.
    ``template`` with ``{ts}``; ``base_epoch``; ``step_s``.
    """
    position = params.get("position", "end")
    if position not in TIMESTAMP_POSITIONS:
        raise ValueError(f"system_timestamp: position {position!r} not in {TIMESTAMP_POSITIONS}")
    template = str(params.get("template", "\n\nCurrent time: {ts}"))
    base = int(params.get("base_epoch", 1_700_000_000))
    step_s = int(params.get("step_s", 60))

    def stamp_for(idx: int) -> str:
        ts = dt.datetime.fromtimestamp(base + idx * step_s, tz=dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        return template.format(ts=ts)

    out: list[Step] = []
    seen: list[tuple[int, list[dict[str, Any]]]] = []  # (idx, original messages) of earlier steps
    for s in steps:
        stamp = stamp_for(s.idx)
        payload = copy.deepcopy(s.payload)
        msgs = _messages(payload)
        original = list(msgs)
        if position in ("tail", "tail_append"):
            if position == "tail_append":
                # An earlier request whose messages are a prefix of this history got its stamp
                # right after them; insert from the back so indices stay valid.
                for idx, prev in reversed(seen):
                    n = len(prev)
                    if n <= len(msgs) and msgs[:n] == prev:
                        msgs.insert(n, {"role": "user", "content": stamp_for(idx).strip()})
            msgs.append({"role": "user", "content": stamp.strip()})
        elif position == "after_tools":
            sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
            msgs.insert(0 if sys_i is None else sys_i + 1, {"role": "system", "content": stamp.strip()})
        else:
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
        seen.append((s.idx, original))
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
