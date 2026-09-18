import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.profile import (
    _lcp_len,
    _union_ms,
    build_profile,
    main,
    render_markdown,
    request_rows,
    think_gaps_ms,
    trace_row,
    turn_row,
)
from analysis.stats import pct
from analysis.tests.conftest import build_two_run_trace
from analysis.trace import TraceError, load_trace


def test_lcp_and_union() -> None:
    assert _lcp_len("", "abc") == 0
    assert _lcp_len("abc", "abc") == 3
    assert _lcp_len("abcd", "abxy") == 2
    assert _lcp_len("x" * 10_000 + "a", "x" * 10_000 + "b") == 10_000
    assert _union_ms([]) == 0
    assert _union_ms([(0, 10)]) == 10
    assert _union_ms([(0, 10), (5, 20), (30, 35)]) == 25  # overlap merged, gap not counted
    assert _union_ms([(30, 35), (0, 10)]) == 15  # order-independent


def test_request_rows(two_run_trace: Path) -> None:
    rows = request_rows(load_trace(two_run_trace))
    assert [r.req for r in rows] == [0, 1, 2, 3]
    r0, r1, r2, r3 = rows

    assert r0.prompt_tokens == 100 and r0.cache_read_tokens == 0 and r0.output_tokens == 12
    assert (r0.ttfb_ms, r0.ttft_ms, r0.model_ms) == (50, 60, 200)
    assert r0.n_tool_calls == 1 and r0.stop_reason == "toolUse"
    assert r0.n_messages == 2 and r0.n_tools_defined == 4
    # first request has no predecessor
    assert r0.prompt_delta_tokens is None and r0.shared_prefix_chars_ratio is None
    assert r0.shared_prefix_msgs is None and r0.tools_changed is None and r0.gap_from_prev_ms is None

    assert r1.prompt_tokens == 140 and r1.cache_read_tokens == 100
    assert r1.prompt_delta_tokens == 40
    assert r1.gap_from_prev_ms == 49  # tool 40 + harness gaps
    assert r1.shared_prefix_msgs == 2  # system + user unchanged, then appended
    assert r1.shared_prefix_chars_ratio is not None and 0.2 < r1.shared_prefix_chars_ratio < 1.0
    assert r1.tools_changed is False

    # superseded retry: no usage/timing, but its payload still counts as the predecessor
    assert r2.outcome == "superseded" and r2.prompt_tokens is None and r2.model_ms is None
    assert r2.gap_from_prev_ms == 30_009  # think time + harness
    assert r3.gap_from_prev_ms is None  # predecessor never ended
    assert r3.shared_prefix_chars_ratio == 1.0 and r3.shared_prefix_msgs == 6  # identical retry
    assert r3.prompt_delta_tokens == 30  # vs last *known* prompt (140), not the superseded None


def test_turn_rows_split_time_directly(two_run_trace: Path) -> None:
    tr = load_trace(two_run_trace)
    t00, t01, t10 = (turn_row(tr, t) for t in tr.turns())

    assert (t00.turn_ms, t00.model_ms, t00.tool_ms, t00.harness_ms, t00.unaccounted_ms) == (
        250,
        200,
        40,
        10,
        0,
    )
    assert (t01.turn_ms, t01.model_ms, t01.tool_ms, t01.harness_ms, t01.unaccounted_ms) == (156, 150, 0, 6, 0)
    # retried turn: 100 ms idle gap + the retry's 5 ms pre-request are neither model, tool nor harness
    assert (t10.turn_ms, t10.model_ms, t10.tool_ms, t10.harness_ms, t10.unaccounted_ms) == (
        232,
        120,
        0,
        7,
        105,
    )
    assert t10.n_requests == 2 and t10.stop_reason == "stop"


def test_turn_row_without_end_or_requests(tmp_path: Path) -> None:
    b = build_two_run_trace()
    # truncate right after the last turn_start to simulate a crash mid-turn
    cut = max(i for i, r in enumerate(b.records) if r["type"] == "turn_start")
    b.records = b.records[: cut + 1]
    tr = load_trace(b.write(tmp_path / "cut.jsonl"))
    last = turn_row(tr, tr.turns()[-1])
    assert last.turn_ms is None and last.harness_ms is None and last.unaccounted_ms is None
    assert last.model_ms == 0 and last.tool_ms == 0


def test_think_gaps_and_trace_row(two_run_trace: Path) -> None:
    tr = load_trace(two_run_trace)
    assert think_gaps_ms(tr) == [30_000]
    row = trace_row(tr, request_rows(tr), [turn_row(tr, t) for t in tr.turns()])
    assert row.n_runs == 2 and row.n_turns == 3 and row.n_requests == 4 and row.n_requests_done == 3
    assert row.n_tools == 1 and row.n_compactions == 1
    assert row.wall_ms == 30_644 and row.active_ms == 250 + 156 + 232
    assert (row.prompt_tokens_first, row.prompt_tokens_last, row.prompt_tokens_max) == (100, 170, 170)
    assert row.model == "fake/fake-1" and row.api == "openai-completions"


def test_build_profile_and_summary(traces_dir: Path) -> None:
    prof = build_profile(sorted(traces_dir.glob("*.jsonl")))
    assert [t.session_id for t in prof.traces] == ["sess-a", "sess-b"]
    assert len(prof.requests) == 8 and len(prof.turns) == 6 and len(prof.tools) == 2
    assert prof.think_gaps == [30_000, 30_000]
    assert prof.warnings == []
    s = prof.summary()
    assert s["n_traces"] == 2
    assert s["session"]["turns"] == pct([3, 3])
    assert s["timing"]["model_ms"]["n"] == 6  # only done requests
    assert s["timing"]["unaccounted_ms_per_turn"]["max"] == 105
    assert s["output"]["outcomes"] == {"done": 6, "superseded": 2}
    assert s["tools"]["bash"]["count"] == 2 and s["tools"]["bash"]["duration_ms"]["p50"] == 40
    assert s["context"]["tools_changed_count"] == 0


def test_api_mismatch_warns_or_fails(tmp_path: Path) -> None:
    b = build_two_run_trace()
    b.records[0]["model"] = {**b.records[0]["model"], "api": "anthropic-messages"}
    p = b.write(tmp_path / "anthropic.jsonl")
    prof = build_profile([p])
    assert len(prof.traces) == 1
    assert prof.warnings and "anthropic-messages" in prof.warnings[0]
    with pytest.raises(TraceError, match="anthropic-messages"):
        build_profile([p], strict_api=True)


def test_context_window_mismatch_warns(tmp_path: Path) -> None:
    b = build_two_run_trace()
    b.records[0]["model"] = {**b.records[0]["model"], "context_window": 1_000_000}
    prof = build_profile([b.write(tmp_path / "wide.jsonl")])
    assert len(prof.traces) == 1
    assert any("context_window=1000000" in w for w in prof.warnings)


def test_min_requests_skips_empty_session(traces_dir: Path) -> None:
    from analysis.tests.conftest import TraceBuilder

    b = TraceBuilder()
    b.header(session_id="empty")
    b.shutdown(0, 0, 0)
    b.write(traces_dir / "empty.jsonl")
    prof = build_profile(sorted(traces_dir.glob("*.jsonl")))
    assert [t.session_id for t in prof.traces] == ["sess-a", "sess-b"]
    assert any("empty.jsonl" in w and "--min-requests" in w for w in prof.warnings)
    assert len(build_profile(sorted(traces_dir.glob("*.jsonl")), min_requests=0).traces) == 3


def test_bad_trace_is_skipped_not_fatal(traces_dir: Path) -> None:
    (traces_dir / "c.jsonl").write_text("garbage\n")
    prof = build_profile(sorted(traces_dir.glob("*.jsonl")))
    assert len(prof.traces) == 2
    assert any("c.jsonl" in w for w in prof.warnings)


def test_render_markdown_has_no_mean_and_all_sections(traces_dir: Path) -> None:
    md = render_markdown(build_profile(sorted(traces_dir.glob("*.jsonl"))))
    for section in ("会话形状", "上下文", "时序", "输出", "工具混合", "每条 trace"):
        assert f"## {section}" in md
    assert "P50 / P95 / P99" in md
    assert "均值" not in md and "mean" not in md.lower()
    assert "| bash | 2 | 0 |" in md


def test_main_writes_artifacts(traces_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(traces_dir), "--out", str(out)]) == 0
    for name in (
        "traces.csv",
        "requests.csv",
        "turns.csv",
        "tools.csv",
        "summary.json",
        "profile.md",
        "meta.json",
    ):
        assert (out / name).exists(), name
    reqs = pd.read_csv(out / "requests.csv")
    assert len(reqs) == 8 and set(reqs["session_id"]) == {"sess-a", "sess-b"}
    meta = json.loads((out / "meta.json").read_text())
    assert len(meta["inputs"]) == 2 and all(len(i["sha256"]) == 64 for i in meta["inputs"])
    assert meta["used"] == ["a.jsonl", "b.jsonl"] and meta["options"] == {
        "strict_api": False,
        "min_requests": 1,
    }
    # every number in profile.md must be reproducible from summary.json
    summary = json.loads((out / "summary.json").read_text())
    assert summary["session"]["turns"]["p50"] == 3


def test_main_no_traces(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty), "--out", str(tmp_path / "out")]) == 2
