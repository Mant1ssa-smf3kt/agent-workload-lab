"""W1 deliverable: the agent-workload profile table, computed from recorded traces.

Reads every trace under a directory, derives per-request / per-turn / per-tool
rows plus a per-trace summary, and writes CSVs, ``summary.json`` and the
Markdown table ``profile.md`` into an output directory. Every number in the
table is traceable to a row in one of the CSVs.

Scope note: all timings here are *recording-side* (cloud model, real tools).
They describe the workload's shape and are not comparable with replay-side
numbers measured against SGLang (docs/decisions.md, 2026-09-18).

    uv run python -m analysis.profile traces/ --out experiments/profile/out
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.log import configure, get_logger
from analysis.stats import Pct, fmt_pct, pct
from analysis.trace import (
    RECORDING_API,
    RECORDING_CONTEXT_WINDOW,
    RequestRecord,
    ToolRecord,
    Trace,
    TraceError,
    Turn,
    iter_trace_paths,
    load_trace,
    prompt_tokens,
)

log = get_logger("analysis.profile")


# ── row types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RequestRow:
    trace: str
    session_id: str
    run: int
    turn: int
    req: int
    outcome: str
    stop_reason: str | None
    prompt_tokens: int | None
    cache_read_tokens: int | None
    output_tokens: int | None
    payload_chars: int | None
    n_messages: int | None
    n_tools_defined: int | None
    ttfb_ms: int | None
    ttft_ms: int | None
    model_ms: int | None
    n_tool_calls: int | None
    text_chars: int | None
    thinking_chars: int | None
    prompt_delta_tokens: int | None
    """prompt_tokens minus the previous request's, within the same trace."""
    shared_prefix_chars_ratio: float | None
    """LCP(chars) of JSON-serialized payload.messages vs previous request / this request's length."""
    shared_prefix_msgs: int | None
    """Number of leading payload.messages identical to the previous request's."""
    tools_changed: bool | None
    """Whether payload.tools differs from the previous request's."""
    gap_from_prev_ms: int | None
    """t_request − previous t_end: the gap that timing=real replays between requests."""


@dataclass(frozen=True)
class TurnRow:
    trace: str
    session_id: str
    run: int
    turn: int
    turn_ms: int | None
    model_ms: int
    tool_ms: int
    harness_ms: int | None
    unaccounted_ms: int | None
    n_requests: int
    n_tools: int
    stop_reason: str | None


@dataclass(frozen=True)
class ToolRow:
    trace: str
    session_id: str
    run: int
    turn: int
    name: str
    duration_ms: int | None
    is_error: bool | None
    args_chars: int
    result_chars: int | None


@dataclass(frozen=True)
class TraceRow:
    trace: str
    session_id: str
    api: str | None
    model: str | None
    pi_version: str
    extension_version: str
    n_runs: int
    n_turns: int
    n_requests: int
    n_requests_done: int
    n_tools: int
    n_compactions: int
    wall_ms: int
    active_ms: int
    prompt_tokens_first: int | None
    prompt_tokens_last: int | None
    prompt_tokens_max: int | None
    payload_chars_max: int | None
    think_gaps_ms: int


# ── per-trace extraction ─────────────────────────────────────────────────


def _span(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else b - a


def _lcp_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    lo, hi = 0, n
    # Binary search on prefix equality: O(log n) slice compares, each O(n) worst case but fast in C.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a[:mid] == b[:mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _messages_json(payload: Any) -> str | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        return None
    return json.dumps(payload["messages"], ensure_ascii=False, separators=(",", ":"))


def _tools_sha(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    tools = payload.get("tools")
    if tools is None:
        return ""
    return hashlib.sha256(json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _leading_equal_messages(prev: Any, cur: Any) -> int | None:
    if not (isinstance(prev, dict) and isinstance(cur, dict)):
        return None
    pm, cm = prev.get("messages"), cur.get("messages")
    if not (isinstance(pm, list) and isinstance(cm, list)):
        return None
    n = 0
    for a, b in zip(pm, cm, strict=False):
        if a != b:
            break
        n += 1
    return n


def request_rows(trace: Trace) -> list[RequestRow]:
    rows: list[RequestRow] = []
    prev: RequestRecord | None = None
    prev_json: str | None = None
    prev_tools: str | None = None
    prev_prompt: int | None = None
    for r in trace.requests:
        usage = r.get("usage")
        pt = prompt_tokens(usage)
        payload = r.get("payload")
        cur_json = _messages_json(payload)
        cur_tools = _tools_sha(payload)
        out = r.get("output")

        shared_ratio: float | None = None
        if prev_json is not None and cur_json:
            shared_ratio = _lcp_len(prev_json, cur_json) / len(cur_json)

        rows.append(
            RequestRow(
                trace=trace.path.name,
                session_id=trace.header["session_id"],
                run=r["run"],
                turn=r["turn"],
                req=r["req"],
                outcome=r["outcome"],
                stop_reason=r.get("stop_reason"),
                prompt_tokens=pt,
                cache_read_tokens=None if usage is None else int(usage["cacheRead"]),
                output_tokens=None if usage is None else int(usage["output"]),
                payload_chars=r.get("payload_chars"),
                n_messages=len(payload["messages"]) if cur_json is not None else None,
                n_tools_defined=(len(payload.get("tools") or []) if isinstance(payload, dict) else None),
                ttfb_ms=_span(r["t_request"], r.get("t_response")),
                ttft_ms=_span(r["t_request"], r.get("t_first_content")),
                model_ms=_span(r["t_request"], r.get("t_end")),
                n_tool_calls=None if out is None else len(out["tool_calls"]),
                text_chars=None if out is None else out["text_chars"],
                thinking_chars=None if out is None else out["thinking_chars"],
                prompt_delta_tokens=None if pt is None or prev_prompt is None else pt - prev_prompt,
                shared_prefix_chars_ratio=shared_ratio,
                shared_prefix_msgs=None
                if prev is None
                else _leading_equal_messages(prev.get("payload"), payload),
                tools_changed=None if prev_tools is None or cur_tools is None else cur_tools != prev_tools,
                gap_from_prev_ms=None if prev is None else _span(prev.get("t_end"), r["t_request"]),
            )
        )
        prev, prev_json, prev_tools = r, cur_json, cur_tools
        if pt is not None:
            prev_prompt = pt  # keep the last *known* count across superseded/aborted requests
    return rows


def _union_ms(intervals: list[tuple[int, int]]) -> int:
    total = 0
    cur_s: int | None = None
    cur_e = 0
    for s, e in sorted(intervals):
        if cur_s is None or s > cur_e:
            if cur_s is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_s is not None:
        total += cur_e - cur_s
    return total


def turn_row(trace: Trace, t: Turn) -> TurnRow:
    """Split a turn into model / tool / harness time, measured directly, plus what is left over.

    harness_ms is *not* a residual. It is the sum of three directly observed gaps:
    turn_start→first request, last request end→first tool start (or turn_end),
    last tool end→turn_end. ``unaccounted_ms`` is total minus the three segments —
    non-zero when e.g. a retried request or sequential tools leave gaps. CLAUDE.md §5.
    """
    t_start = t.start["t"]
    t_end = t.end["t"] if t.end else None
    turn_ms = _span(t_start, t_end)

    finished = [(int(r["t_request"]), e) for r in t.requests if (e := r.get("t_end")) is not None]
    model_ms = sum(e - s for s, e in finished)
    tool_iv = [(int(x["t_start"]), e) for x in t.tools if (e := x.get("t_end")) is not None]
    tool_ms = _union_ms(tool_iv)

    harness: int | None = None
    if t.requests and finished and t_end is not None:
        pre = int(t.requests[0]["t_request"]) - t_start
        last_model_end = finished[-1][1]
        if tool_iv:
            post_model = min(s for s, _ in tool_iv) - last_model_end
            post_tool = t_end - max(e for _, e in tool_iv)
        else:
            post_model = t_end - last_model_end
            post_tool = 0
        harness = pre + post_model + post_tool

    unaccounted = None if turn_ms is None or harness is None else turn_ms - model_ms - tool_ms - harness
    return TurnRow(
        trace=trace.path.name,
        session_id=trace.header["session_id"],
        run=t.run,
        turn=t.turn,
        turn_ms=turn_ms,
        model_ms=model_ms,
        tool_ms=tool_ms,
        harness_ms=harness,
        unaccounted_ms=unaccounted,
        n_requests=len(t.requests),
        n_tools=len(t.tools),
        stop_reason=t.end.get("stop_reason") if t.end else None,
    )


def tool_row(trace: Trace, x: ToolRecord) -> ToolRow:
    return ToolRow(
        trace=trace.path.name,
        session_id=trace.header["session_id"],
        run=x["run"],
        turn=x["turn"],
        name=x["name"],
        duration_ms=_span(x["t_start"], x.get("t_end")),
        is_error=x.get("is_error"),
        args_chars=x["args_chars"],
        result_chars=x.get("result_chars"),
    )


def think_gaps_ms(trace: Trace) -> list[int]:
    """Human think time: agent_settled of run k → user_prompt of run k+1."""
    settled: dict[int, int] = {int(r["run"]): int(r["t"]) for r in trace.of_type("agent_settled")}
    gaps: list[int] = []
    for up in trace.of_type("user_prompt"):
        run = int(up["run"])
        if run - 1 in settled:
            gaps.append(int(up["t"]) - settled[run - 1])
    return gaps


def trace_row(trace: Trace, reqs: list[RequestRow], turns: list[TurnRow]) -> TraceRow:
    pts = [r.prompt_tokens for r in reqs if r.prompt_tokens is not None]
    pcs = [r.payload_chars for r in reqs if r.payload_chars is not None]
    model = trace.header.get("model")
    return TraceRow(
        trace=trace.path.name,
        session_id=trace.header["session_id"],
        api=trace.api,
        model=f"{model['provider']}/{model['id']}" if model else None,
        pi_version=trace.header["pi_version"],
        extension_version=trace.header["extension_version"],
        n_runs=trace.n_runs,
        n_turns=len(turns),
        n_requests=len(reqs),
        n_requests_done=sum(1 for r in reqs if r.outcome == "done"),
        n_tools=len(trace.tools),
        n_compactions=trace.n_compactions,
        wall_ms=trace.wall_ms,
        active_ms=sum(t.turn_ms for t in turns if t.turn_ms is not None),
        prompt_tokens_first=pts[0] if pts else None,
        prompt_tokens_last=pts[-1] if pts else None,
        prompt_tokens_max=max(pts) if pts else None,
        payload_chars_max=max(pcs) if pcs else None,
        think_gaps_ms=len(think_gaps_ms(trace)),
    )


# ── aggregation ───────────────────────────────────────────────────────────


@dataclass
class Profile:
    traces: list[TraceRow]
    requests: list[RequestRow]
    turns: list[TurnRow]
    tools: list[ToolRow]
    think_gaps: list[int]
    warnings: list[str]

    def summary(self) -> dict[str, Any]:
        rq, tn, tl = self.requests, self.turns, self.tools
        done = [r for r in rq if r.outcome == "done"]
        by_tool: dict[str, dict[str, Any]] = {}
        for name, count in Counter(x.name for x in tl).most_common():
            durs = [x.duration_ms for x in tl if x.name == name]
            errs = sum(1 for x in tl if x.name == name and x.is_error)
            by_tool[name] = {"count": count, "errors": errs, "duration_ms": pct(durs)}
        return {
            "n_traces": len(self.traces),
            "apis": sorted({t.api or "unknown" for t in self.traces}),
            "models": sorted({t.model or "unknown" for t in self.traces}),
            "pi_versions": sorted({t.pi_version for t in self.traces}),
            "session": {
                "turns": pct(t.n_turns for t in self.traces),
                "requests": pct(t.n_requests for t in self.traces),
                "tools": pct(t.n_tools for t in self.traces),
                "compactions": pct(t.n_compactions for t in self.traces),
                "wall_s": pct(t.wall_ms / 1000 for t in self.traces),
                "active_s": pct(t.active_ms / 1000 for t in self.traces),
            },
            "context": {
                "prompt_tokens_first": pct(t.prompt_tokens_first for t in self.traces),
                "prompt_tokens_last": pct(t.prompt_tokens_last for t in self.traces),
                "prompt_tokens_max": pct(t.prompt_tokens_max for t in self.traces),
                "prompt_tokens": pct(r.prompt_tokens for r in done),
                "prompt_delta_tokens": pct(r.prompt_delta_tokens for r in done),
                "payload_chars": pct(r.payload_chars for r in done),
                "n_messages": pct(r.n_messages for r in done),
                "shared_prefix_chars_ratio": pct(r.shared_prefix_chars_ratio for r in done),
                "shared_prefix_msgs": pct(r.shared_prefix_msgs for r in done),
                "tools_changed_count": sum(1 for r in done if r.tools_changed),
            },
            "timing": {
                "ttfb_ms": pct(r.ttfb_ms for r in done),
                "ttft_ms": pct(r.ttft_ms for r in done),
                "model_ms": pct(r.model_ms for r in done),
                "turn_ms": pct(t.turn_ms for t in tn),
                "tool_ms_per_turn": pct(t.tool_ms for t in tn),
                "harness_ms_per_turn": pct(t.harness_ms for t in tn),
                "unaccounted_ms_per_turn": pct(t.unaccounted_ms for t in tn),
                "gap_from_prev_ms": pct(r.gap_from_prev_ms for r in rq),
                "think_gap_ms": pct(self.think_gaps),
            },
            "output": {
                "output_tokens": pct(r.output_tokens for r in done),
                "text_chars": pct(r.text_chars for r in done),
                "thinking_chars": pct(r.thinking_chars for r in done),
                "tool_calls_per_request": pct(r.n_tool_calls for r in done),
                "outcomes": dict(Counter(r.outcome for r in rq)),
                "stop_reasons": dict(Counter(r.stop_reason or "null" for r in rq)),
            },
            "tools": by_tool,
            "warnings": self.warnings,
        }


def build_profile(paths: list[Path], strict_api: bool = False, min_requests: int = 1) -> Profile:
    """``min_requests``: traces with fewer requests (e.g. a session opened and quit) are skipped
    and listed in ``warnings``. Filtering happens here, never on the files (CLAUDE.md §8.2)."""
    traces: list[TraceRow] = []
    requests: list[RequestRow] = []
    turns: list[TurnRow] = []
    tools: list[ToolRow] = []
    gaps: list[int] = []
    warnings: list[str] = []
    for p in paths:
        try:
            tr = load_trace(p)
        except TraceError as e:
            warnings.append(f"skipped {p.name}: {e}")
            log.warning("skipped trace", path=str(p), error=str(e))
            continue
        if tr.api != RECORDING_API:
            msg = f"{p.name}: recorded via api={tr.api!r}, expected {RECORDING_API!r} (docs/decisions.md)"
            if strict_api:
                raise TraceError(msg)
            warnings.append(msg)
            log.warning("unexpected recording api", path=str(p), api=tr.api)
        if tr.context_window != RECORDING_CONTEXT_WINDOW:
            msg = (
                f"{p.name}: model.context_window={tr.context_window}, expected {RECORDING_CONTEXT_WINDOW} "
                "(modelOverrides not applied? docs/decisions.md)"
            )
            warnings.append(msg)
            log.warning("unexpected context window", path=str(p), context_window=tr.context_window)
        rq = request_rows(tr)
        if len(rq) < min_requests:
            warnings.append(f"skipped {p.name}: {len(rq)} requests < --min-requests {min_requests}")
            log.warning("skipped trace", path=str(p), requests=len(rq), min_requests=min_requests)
            continue
        tn = [turn_row(tr, t) for t in tr.turns()]
        requests.extend(rq)
        turns.extend(tn)
        tools.extend(tool_row(tr, x) for x in tr.tools)
        gaps.extend(think_gaps_ms(tr))
        traces.append(trace_row(tr, rq, tn))
        log.info("profiled trace", path=str(p), requests=len(rq), turns=len(tn), tools=len(tr.tools))
    return Profile(
        traces=traces, requests=requests, turns=turns, tools=tools, think_gaps=gaps, warnings=warnings
    )


# ── rendering ─────────────────────────────────────────────────────────────


def _row(label: str, p: Pct, unit: str = "", digits: int = 0) -> str:
    return f"| {label} | {fmt_pct(p, unit, digits)} |"


def render_markdown(profile: Profile) -> str:
    s = profile.summary()
    L: list[str] = []
    L.append("# Agent 负载画像（录制侧）")
    L.append("")
    L.append(
        f"来源：{s['n_traces']} 条 trace · api={', '.join(s['apis'])} · "
        f"model={', '.join(s['models'])} · pi={', '.join(s['pi_versions'])}"
    )
    L.append("")
    L.append("所有数字为 P50 / P95 / P99 (n)。")
    L.append("时序为录制侧（云端模型 + 真实工具），只描述负载形状，不与重放侧比较。")
    L.append("`prompt_tokens` = provider 上报的 input + cacheRead，是云端 tokenizer 口径。")
    L.append("")
    if s["warnings"]:
        L.append("> **警告**")
        L.extend(f"> - {w}" for w in s["warnings"])
        L.append("")

    L.append("## 会话形状")
    L.append("")
    L.append("| 指标 | P50 / P95 / P99 (n) |")
    L.append("|---|---|")
    L.append(_row("每会话轮数", s["session"]["turns"]))
    L.append(_row("每会话请求数", s["session"]["requests"]))
    L.append(_row("每会话工具调用数", s["session"]["tools"]))
    L.append(_row("每会话 compaction 次数", s["session"]["compactions"]))
    L.append(_row("会话墙钟", s["session"]["wall_s"], " s", 1))
    L.append(_row("会话活跃时间 (Σ turn)", s["session"]["active_s"], " s", 1))
    L.append("")

    L.append("## 上下文")
    L.append("")
    L.append("| 指标 | P50 / P95 / P99 (n) |")
    L.append("|---|---|")
    L.append(_row("首轮 prompt tokens", s["context"]["prompt_tokens_first"]))
    L.append(_row("末轮 prompt tokens", s["context"]["prompt_tokens_last"]))
    L.append(_row("最大 prompt tokens", s["context"]["prompt_tokens_max"]))
    L.append(_row("每请求 prompt tokens", s["context"]["prompt_tokens"]))
    L.append(_row("每轮 prompt 增量 tokens", s["context"]["prompt_delta_tokens"]))
    L.append(_row("payload 大小", s["context"]["payload_chars"], " chars"))
    L.append(_row("payload 消息数", s["context"]["n_messages"]))
    L.append(
        _row("跨轮共享前缀比例 (chars, messages JSON)", s["context"]["shared_prefix_chars_ratio"], "", 3)
    )
    L.append(_row("跨轮相同前导消息数", s["context"]["shared_prefix_msgs"]))
    L.append(f"| tools 定义在相邻请求间变化的次数 | {s['context']['tools_changed_count']} |")
    L.append("")

    L.append("## 时序")
    L.append("")
    L.append("| 指标 | P50 / P95 / P99 (n) |")
    L.append("|---|---|")
    L.append(_row("TTFB（响应头）", s["timing"]["ttfb_ms"], " ms"))
    L.append(_row("TTFT（首个内容 delta，不含 thinking）", s["timing"]["ttft_ms"], " ms"))
    L.append(_row("模型时间 / 请求", s["timing"]["model_ms"], " ms"))
    L.append(_row("单轮总时长", s["timing"]["turn_ms"], " ms"))
    L.append(_row("工具时间 / 轮（区间并集）", s["timing"]["tool_ms_per_turn"], " ms"))
    L.append(_row("harness 开销 / 轮（直接测量）", s["timing"]["harness_ms_per_turn"], " ms"))
    L.append(_row("未归因 / 轮（总 − 三段）", s["timing"]["unaccounted_ms_per_turn"], " ms"))
    L.append(_row("请求间隔（上一请求结束 → 下一请求发出）", s["timing"]["gap_from_prev_ms"], " ms"))
    L.append(_row("人类思考间隔（run 间）", s["timing"]["think_gap_ms"], " ms"))
    L.append("")

    L.append("## 输出")
    L.append("")
    L.append("| 指标 | P50 / P95 / P99 (n) |")
    L.append("|---|---|")
    L.append(_row("output tokens / 请求", s["output"]["output_tokens"]))
    L.append(_row("文本输出", s["output"]["text_chars"], " chars"))
    L.append(_row("thinking 输出", s["output"]["thinking_chars"], " chars"))
    L.append(_row("工具调用数 / 请求", s["output"]["tool_calls_per_request"]))
    L.append(f"| 请求 outcome | {json.dumps(s['output']['outcomes'], ensure_ascii=False)} |")
    L.append(f"| stop_reason | {json.dumps(s['output']['stop_reasons'], ensure_ascii=False)} |")
    L.append("")

    L.append("## 工具混合")
    L.append("")
    L.append("| 工具 | 次数 | 错误 | 耗时 P50 / P95 / P99 |")
    L.append("|---|---|---|---|")
    for name, v in s["tools"].items():
        L.append(f"| {name} | {v['count']} | {v['errors']} | {fmt_pct(v['duration_ms'], ' ms')} |")
    L.append("")

    L.append("## 每条 trace")
    L.append("")
    L.append(
        "| trace | model | runs | turns | reqs (done) | tools | compact | wall s "
        "| prompt tokens first→last (max) |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    for t in profile.traces:
        L.append(
            f"| {t.trace} | {t.model} | {t.n_runs} | {t.n_turns} | {t.n_requests} ({t.n_requests_done}) | "
            f"{t.n_tools} | {t.n_compactions} | {t.wall_ms / 1000:.1f} | "
            f"{t.prompt_tokens_first}→{t.prompt_tokens_last} ({t.prompt_tokens_max}) |"
        )
    L.append("")
    return "\n".join(L)


# ── artifact writing ──────────────────────────────────────────────────────


def _git_head(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True, timeout=5
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_profile(profile: Profile, out: Path, inputs: list[Path], options: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(r) for r in profile.traces]).to_csv(out / "traces.csv", index=False)
    pd.DataFrame([asdict(r) for r in profile.requests]).to_csv(out / "requests.csv", index=False)
    pd.DataFrame([asdict(r) for r in profile.turns]).to_csv(out / "turns.csv", index=False)
    pd.DataFrame([asdict(r) for r in profile.tools]).to_csv(out / "tools.csv", index=False)
    (out / "summary.json").write_text(
        json.dumps(profile.summary(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "profile.md").write_text(render_markdown(profile), encoding="utf-8")
    # Provenance: which inputs, which analysis code. GPU fields are N/A for a recording-side artifact.
    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "analysis_git_commit": _git_head(Path(__file__).resolve().parent),
        "python": sys.version.split()[0],
        "inputs": [{"path": str(p), "sha256": _sha256_file(p), "bytes": p.stat().st_size} for p in inputs],
        "used": [t.trace for t in profile.traces],
        "options": options,
        "warnings": profile.warnings,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote profile", out=str(out), traces=len(profile.traces), warnings=len(profile.warnings))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("traces", type=Path, help="trace file or directory (searched recursively for *.jsonl)")
    ap.add_argument(
        "--out", type=Path, required=True, help="output directory for CSVs, summary.json, profile.md"
    )
    ap.add_argument(
        "--strict-api",
        action="store_true",
        help=f"fail instead of warn when a trace was not recorded via {RECORDING_API}",
    )
    ap.add_argument(
        "--min-requests",
        type=int,
        default=1,
        help="skip traces with fewer requests (default 1: an opened-and-quit session is not a trajectory)",
    )
    args = ap.parse_args(argv)
    configure()
    paths = iter_trace_paths(args.traces)
    if not paths:
        log.error("no traces found", root=str(args.traces))
        return 2
    profile = build_profile(paths, strict_api=args.strict_api, min_requests=args.min_requests)
    if not profile.traces:
        log.error("no loadable traces", root=str(args.traces), warnings=profile.warnings)
        return 2
    write_profile(
        profile, args.out, paths, {"strict_api": args.strict_api, "min_requests": args.min_requests}
    )
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
