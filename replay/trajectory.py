"""Trace → replayable trajectory: an ordered list of steps with normalized payloads and gaps.

Fidelity contract (CLAUDE.md §4): we reproduce the *token sequence* pi sent and the
*timing* between requests; we do not reproduce model behaviour. The served model's
outputs are discarded — the next step's history is the recorded one.
"""

from __future__ import annotations

import fnmatch
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from analysis.trace import RequestRecord, Trace, TraceError, iter_trace_paths, load_trace, prompt_tokens
from replay.config import Config

# Request-body keys we forward to the server. Everything else is provider-specific
# (zai: tool_stream / thinking; OpenAI: store / max_completion_tokens) and is dropped.
FORWARDED_KEYS = frozenset(
    {
        "messages",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "stream",
        "stream_options",
        "max_tokens",
        "temperature",
        "top_p",
        "seed",
        "stop",
        "response_format",
    }
)

COMPACTION_INSTRUCTION = (
    "Summarize the conversation so far for a fresh context window. Preserve decisions, "
    "file paths, open problems and next steps."
)


@dataclass(frozen=True)
class Recorded:
    """What the recording side observed for this step, for reference only (cloud tokenizer)."""

    prompt_tokens: int | None
    cache_read_tokens: int | None
    output_tokens: int | None
    ttft_ms: int | None
    model_ms: int | None
    payload_chars: int | None


@dataclass(frozen=True)
class Step:
    trajectory: str
    idx: int
    kind: str
    """``request`` (a recorded provider request) or ``compaction`` (synthesized summary call)."""
    run: int
    turn: int
    req: int | None
    gap_before_ms: int
    """Recorded wall-clock gap from the previous step's end to this request's send (0 for the first)."""
    payload: dict[str, Any]
    recorded: Recorded
    synthetic: bool = False


@dataclass
class Trajectory:
    id: str
    path: Path
    session_id: str
    pi_version: str
    extension_version: str
    recorded_model: str | None
    steps: list[Step] = field(default_factory=list)
    dropped_requests: int = 0
    """Recorded requests not replayed (outcome != done: no usage/timing to honour)."""
    dropped_keys: list[str] = field(default_factory=list)
    """Provider-specific payload keys removed during normalization (union over steps)."""

    @property
    def n_synthetic(self) -> int:
        return sum(1 for s in self.steps if s.synthetic)


# ── payload normalization ─────────────────────────────────────────────────


def normalize_payload(
    payload: dict[str, Any], cfg: Config, max_tokens: int
) -> tuple[dict[str, Any], list[str]]:
    """Recorded openai-completions body → body for the replay server.

    Returns the new body and the list of keys that were dropped.
    """
    r = cfg.replay
    body: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in payload.items():
        if key in FORWARDED_KEYS:
            body[key] = value
        elif key not in ("model", "max_completion_tokens"):  # those two are replaced below
            dropped.append(key)

    body["model"] = cfg.server.model
    body["messages"] = [_normalize_message(m) for m in body.get("messages", [])]
    body["max_tokens"] = max(1, int(max_tokens))
    body["temperature"] = r.temperature
    body["stream"] = r.stream
    if r.stream:
        body["stream_options"] = {"include_usage": True}
    else:
        body.pop("stream_options", None)
    if r.ignore_eos:
        body["ignore_eos"] = True
    for key, value in cfg.server.extra_body.items():
        body[key] = value
    return body, dropped


def _normalize_message(m: dict[str, Any]) -> dict[str, Any]:
    out = dict(m)
    if out.get("role") == "developer":
        out["role"] = "system"
    return out


# ── step construction ────────────────────────────────────────────────────


def _max_tokens_for(cfg: Config, recorded_output: int | None) -> int:
    if cfg.replay.output_mode == "fixed" or recorded_output is None:
        return cfg.replay.output_tokens
    return max(1, recorded_output)


def _recorded(r: RequestRecord) -> Recorded:
    usage = r.get("usage")
    t_req = r["t_request"]
    t_fc = r.get("t_first_content")
    t_end = r.get("t_end")
    return Recorded(
        prompt_tokens=prompt_tokens(usage),
        cache_read_tokens=None if usage is None else int(usage["cacheRead"]),
        output_tokens=None if usage is None else int(usage["output"]),
        ttft_ms=None if t_fc is None else t_fc - t_req,
        model_ms=None if t_end is None else t_end - t_req,
        payload_chars=r.get("payload_chars"),
    )


def synthesize_compaction_payload(
    prev_payload: dict[str, Any], prev_prompt_tokens: int | None, target_input_tokens: int
) -> tuple[dict[str, Any], int]:
    """A summary-call stand-in of roughly ``target_input_tokens`` built from the previous
    request's messages: system prompt + the earliest messages up to the size budget + a
    summarize instruction. It shares its prefix with what the server has just seen, which is
    what pi's own summary call (verbatim old messages) does too. Returns (payload, est_tokens).

    ``tools`` is kept on purpose: chat templates render the tool list inside the system
    segment, so dropping it would break the shared prefix from the first few thousand
    tokens (measured 0.197 hit vs ~0.99 in baseline-c1; docs/decisions.md 2026-09-19).
    """
    messages: list[dict[str, Any]] = list(prev_payload.get("messages", []))
    prev_chars = len(json.dumps(messages, ensure_ascii=False))
    cpt = prev_chars / prev_prompt_tokens if prev_prompt_tokens else 4.0  # chars per token
    budget_chars = int(target_input_tokens * cpt)

    kept: list[dict[str, Any]] = []
    used = 0
    for m in messages:
        size = len(json.dumps(m, ensure_ascii=False))
        if kept and used + size > budget_chars:
            break
        kept.append(m)
        used += size
    kept.append({"role": "user", "content": COMPACTION_INSTRUCTION})
    body = dict(prev_payload)
    body["messages"] = kept
    return body, int(used / cpt) if cpt else 0


def build_trajectory(trace: Trace, cfg: Config) -> Trajectory:
    model = trace.header.get("model")
    traj = Trajectory(
        id=trace.path.stem,
        path=trace.path,
        session_id=trace.header["session_id"],
        pi_version=trace.header["pi_version"],
        extension_version=trace.header["extension_version"],
        recorded_model=f"{model['provider']}/{model['id']}" if model else None,
    )
    dropped: set[str] = set()
    prev_end: int | None = None
    prev_req: RequestRecord | None = None
    last_turn_end_t: int | None = None
    idx = 0

    for rec in trace.records:
        t = rec["type"]
        if t == "turn_end":
            last_turn_end_t = int(rec["t"])
        elif t == "request":
            r: RequestRecord = rec  # type: ignore[assignment]
            if r["outcome"] != "done" or r.get("usage") is None or r.get("t_end") is None:
                traj.dropped_requests += 1
                continue
            recorded = _recorded(r)
            body, dk = normalize_payload(r["payload"], cfg, _max_tokens_for(cfg, recorded.output_tokens))
            dropped.update(dk)
            gap = 0 if prev_end is None else max(0, int(r["t_request"]) - prev_end)
            traj.steps.append(
                Step(
                    trajectory=traj.id,
                    idx=idx,
                    kind="request",
                    run=r["run"],
                    turn=r["turn"],
                    req=r["req"],
                    gap_before_ms=gap,
                    payload=body,
                    recorded=recorded,
                )
            )
            idx += 1
            prev_end = int(r["t_end"])  # type: ignore[arg-type]
            prev_req = r
        elif t == "compaction" and cfg.replay.compaction == "synthesize" and prev_req is not None:
            usage = rec.get("usage") or {}
            target_in = int(usage.get("input") or 0)
            target_out = int(usage.get("output") or 0)
            if target_in <= 0:
                continue
            # The summary call ran between the last turn_end and this record.
            start = last_turn_end_t if last_turn_end_t is not None else int(rec["t"])
            base, est = synthesize_compaction_payload(
                prev_req["payload"], prompt_tokens(prev_req.get("usage")), target_in
            )
            body, dk = normalize_payload(base, cfg, _max_tokens_for(cfg, target_out))
            dropped.update(dk)
            gap = 0 if prev_end is None else max(0, start - prev_end)
            traj.steps.append(
                Step(
                    trajectory=traj.id,
                    idx=idx,
                    kind="compaction",
                    run=int(rec["run"]),
                    turn=int(prev_req["turn"]),
                    req=None,
                    gap_before_ms=gap,
                    payload=body,
                    recorded=Recorded(
                        prompt_tokens=target_in,
                        cache_read_tokens=int(usage.get("cacheRead") or 0),
                        output_tokens=target_out,
                        ttft_ms=None,
                        model_ms=int(rec["t"]) - start,
                        payload_chars=est,
                    ),
                    synthetic=True,
                )
            )
            idx += 1
            prev_end = int(rec["t"])

    traj.dropped_keys = sorted(dropped)
    return traj


# ── loading a set ─────────────────────────────────────────────────────────


@dataclass
class LoadReport:
    trajectories: list[Trajectory]
    skipped: list[str]


def load_trajectories(cfg: Config, root: Path) -> LoadReport:
    """Select, order and build trajectories per ``cfg.traces``, then apply ``cfg.transform``.
    Skips are reported, never fatal; an unknown transform is a ``ConfigError``."""
    from replay.config import ConfigError
    from replay.transforms import TRANSFORMS, apply_transform

    if cfg.transform.name not in TRANSFORMS:
        raise ConfigError(f"transform.name {cfg.transform.name!r} unknown; known: {sorted(TRANSFORMS)}")
    tc = cfg.traces
    base = root / tc.dir if not Path(tc.dir).is_absolute() else Path(tc.dir)
    paths = [p for p in iter_trace_paths(base) if fnmatch.fnmatch(p.name, tc.include)]
    if tc.order == "shuffle":
        random.Random(cfg.replay.seed).shuffle(paths)
    trajs: list[Trajectory] = []
    skipped: list[str] = []
    for p in paths:
        try:
            tr = load_trace(p)
        except TraceError as e:
            skipped.append(f"{p.name}: {e}")
            continue
        traj = build_trajectory(tr, cfg)
        traj.steps = apply_transform(cfg.transform.name, cfg.transform.params, traj.steps)
        n_real = sum(1 for s in traj.steps if not s.synthetic)
        if n_real < tc.min_requests:
            skipped.append(f"{p.name}: {n_real} requests < min_requests {tc.min_requests}")
            continue
        trajs.append(traj)
    if tc.limit is not None:
        trajs = trajs[: tc.limit]
    return LoadReport(trajectories=trajs, skipped=skipped)
