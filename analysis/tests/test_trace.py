from pathlib import Path

import pytest

from analysis.trace import TraceError, iter_trace_paths, load_trace, prompt_tokens


def test_load_and_views(two_run_trace: Path) -> None:
    tr = load_trace(two_run_trace)
    assert tr.header["schema"] == 1
    assert tr.header["session_id"] == "sess-1"
    assert tr.api == "openai-completions"
    assert tr.n_runs == 2
    assert tr.n_compactions == 1
    assert len(tr.requests) == 4
    assert len(tr.tools) == 1
    assert len(tr.contexts) == 3
    assert tr.shutdown is not None and tr.shutdown["n_requests"] == 4
    assert tr.wall_ms == 30_644


def test_turn_grouping(two_run_trace: Path) -> None:
    turns = load_trace(two_run_trace).turns()
    assert [t.key for t in turns] == [(0, 0), (0, 1), (1, 0)]
    t00, t01, t10 = turns
    assert len(t00.requests) == 1 and len(t00.tools) == 1 and t00.end is not None
    assert t00.end["stop_reason"] == "toolUse"
    assert len(t01.requests) == 1 and t01.tools == []
    # retried turn keeps both the superseded and the real request, in order
    assert [r["outcome"] for r in t10.requests] == ["superseded", "done"]
    assert t10.context is not None and t10.context["n_messages"] == 5


def test_prompt_tokens_is_input_plus_cache_read() -> None:
    assert prompt_tokens(None) is None
    assert (
        prompt_tokens({"input": 61, "output": 12, "cacheRead": 40, "cacheWrite": 0, "totalTokens": 113})
        == 101
    )


@pytest.mark.parametrize(
    ("lines", "match"),
    [
        ([], "empty"),
        (['{"type":"agent_start","t":1,"seq":0}'], "expected 'header'"),
        (['{"type":"header","schema":2,"t":1,"seq":0}'], "schema 2 unsupported"),
        (['{"type":"header","schema":1,"t":1,"seq":0}', '{"type":"shutdown","t":2,"seq":5}'], "seq=5"),
        (['{"type":"header","schema":1,"t":1,"seq":0}', "not json"], "invalid JSON"),
        (['{"type":"header","schema":1,"t":1,"seq":0}', "[1,2]"], "without 'type'"),
    ],
)
def test_invariants(tmp_path: Path, lines: list[str], match: str) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text("\n".join(lines) + "\n")
    with pytest.raises(TraceError, match=match):
        load_trace(p)


def test_iter_trace_paths(traces_dir: Path) -> None:
    ps = iter_trace_paths(traces_dir)
    assert [p.name for p in ps] == ["a.jsonl", "b.jsonl"]
    assert iter_trace_paths(ps[0]) == [ps[0]]
    (traces_dir / "README.md").write_text("ignored")
    assert len(iter_trace_paths(traces_dir)) == 2
