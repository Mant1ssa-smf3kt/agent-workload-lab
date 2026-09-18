import json
from pathlib import Path
from typing import Any

from analysis.tests.conftest import A0, A1, SYS, T0, U0, U1, TraceBuilder, build_two_run_trace
from analysis.trace import load_trace
from replay.config import Config, ReplayConfig, ServerConfig, TracesConfig
from replay.trajectory import (
    COMPACTION_INSTRUCTION,
    build_trajectory,
    load_trajectories,
    normalize_payload,
    synthesize_compaction_payload,
)

ZAI_PAYLOAD = {
    "model": "glm-5.2",
    "messages": [SYS, U0, A0, T0],
    "stream": True,
    "stream_options": {"include_usage": True},
    "max_tokens": 8192,
    "tools": [{"type": "function", "function": {"name": "bash"}}],
    "tool_stream": True,
    "thinking": {"type": "disabled"},
}


def test_normalize_drops_provider_keys_and_sets_replay_fields() -> None:
    cfg = Config(name="t")
    body, dropped = normalize_payload(ZAI_PAYLOAD, cfg, max_tokens=42)
    assert sorted(dropped) == ["thinking", "tool_stream"]
    assert body["model"] == "Qwen/Qwen3-8B-FP8"
    assert body["max_tokens"] == 42 and body["temperature"] == 0.0
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert body["ignore_eos"] is True
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["messages"] == [SYS, U0, A0, T0] and body["tools"] == ZAI_PAYLOAD["tools"]
    assert "thinking" not in body and "tool_stream" not in body


def test_normalize_openai_style_and_non_stream() -> None:
    cfg = Config(
        name="t", replay=ReplayConfig(stream=False, ignore_eos=False), server=ServerConfig(extra_body={})
    )
    body, dropped = normalize_payload(
        {
            "model": "gpt",
            "messages": [{"role": "developer", "content": "sys"}],
            "store": False,
            "max_completion_tokens": 9,
        },
        cfg,
        max_tokens=5,
    )
    assert dropped == ["store"]
    assert body["messages"][0]["role"] == "system"
    assert body["max_tokens"] == 5 and body["stream"] is False
    assert "stream_options" not in body and "ignore_eos" not in body and "max_completion_tokens" not in body


def test_build_trajectory_steps_gaps_and_synthetic_compaction(two_run_trace: Path) -> None:
    cfg = Config(name="t")
    traj = build_trajectory(load_trace(two_run_trace), cfg)
    kinds = [(s.idx, s.kind, s.req, s.synthetic) for s in traj.steps]
    # 3 done requests (superseded one dropped); fixture compaction has usage=null → not synthesizable
    assert kinds == [(0, "request", 0, False), (1, "request", 1, False), (2, "request", 3, False)]
    assert traj.dropped_requests == 1
    assert traj.dropped_keys == []  # builder payloads carry no provider extras

    s0, s1, s2 = traj.steps
    assert s0.gap_before_ms == 0
    assert s1.gap_before_ms == 49  # tool 40 + harness gaps, from the recorded timestamps
    assert s2.gap_before_ms == 30_519 - 405  # think time + superseded retry gap
    assert s0.payload["max_tokens"] == 12 and s1.payload["max_tokens"] == 8 and s2.payload["max_tokens"] == 3
    assert s0.recorded.prompt_tokens == 100 and s1.recorded.cache_read_tokens == 100
    assert s1.recorded.ttft_ms == 55 and s1.recorded.model_ms == 150


def _trace_with_compaction(tmp_path: Path, mode: str = "synthesize") -> tuple[Config, Path]:
    """Run 0: one request (prompt 1000 tokens) → tool → turn_end → compaction (usage in 400 / out 50)
    12 s later → run 1: one request."""
    b = TraceBuilder()
    b.header()
    b.user_prompt(0, "go")
    b.agent_start(0)
    b.turn_start(0, 0)
    long_msgs: list[dict[str, Any]] = [SYS, U0, A0, T0, A1, U1, A0, T0]
    b.request(
        0,
        0,
        long_msgs,
        content=[{"type": "text", "text": "ok"}],
        prompt_tokens=1000,
        output_tokens=5,
        model_ms=100,
        pre=5,
    )
    b.tool(0, 0, "c", "bash", {"command": "x"}, duration=30, pre=2)
    b.turn_end(0, 0, "toolUse", 1, dt=3)
    b.records.append(
        {
            "type": "compaction",
            "run": 0,
            "reason": "threshold",
            "will_retry": False,
            "from_extension": False,
            "tokens_before": 1000,
            "summary_chars": 300,
            "usage": {"input": 400, "output": 50, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 450},
            "t": b.tick(12_000),
            "seq": b.seq,
        }
    )
    b.seq += 1
    b.agent_end(0, 3)
    b.user_prompt(1, "more", dt=5_000)
    b.agent_start(1)
    b.turn_start(1, 0)
    b.request(
        1,
        0,
        [SYS, {"role": "user", "content": "summary…"}, U1],
        content=[{"type": "text", "text": "done"}],
        prompt_tokens=300,
        output_tokens=4,
        model_ms=80,
        pre=5,
    )
    b.turn_end(1, 0, "stop", 0)
    b.agent_end(1, 2)
    b.shutdown(2, 2, 1)
    p = b.write(tmp_path / "compact.jsonl")
    return Config(name="t", replay=ReplayConfig(compaction=mode)), p  # type: ignore[arg-type]


def test_synthetic_compaction_step(tmp_path: Path) -> None:
    cfg, p = _trace_with_compaction(tmp_path)
    traj = build_trajectory(load_trace(p), cfg)
    assert [s.kind for s in traj.steps] == ["request", "compaction", "request"]
    s0, comp, s2 = traj.steps
    assert comp.synthetic and comp.req is None and comp.run == 0 and comp.turn == 0
    assert comp.payload["max_tokens"] == 50
    assert "tools" not in comp.payload
    assert comp.payload["messages"][0] == SYS
    assert comp.payload["messages"][-1] == {"role": "user", "content": COMPACTION_INSTRUCTION}
    # sized to ~400 of the 1000-token previous prompt: strictly fewer messages than the original
    assert 1 < len(comp.payload["messages"]) - 1 < len(s0.payload["messages"])
    assert comp.recorded.prompt_tokens == 400 and comp.recorded.output_tokens == 50
    # gap: summary call started at turn_end (request end +2 +30 +3 = 35 ms later)
    assert comp.gap_before_ms == 35
    assert comp.recorded.model_ms == 12_000
    # next request's gap is measured from the compaction record
    assert (
        s2.gap_before_ms == 5_000 + 1 + 0 + 5 + 1 + 0
    )  # agent_end/settled(+1), user_prompt(+5000), agent_start(+1), pre(+5)
    assert traj.n_synthetic == 1


def test_compaction_skip_mode(tmp_path: Path) -> None:
    cfg, p = _trace_with_compaction(tmp_path, mode="skip")
    traj = build_trajectory(load_trace(p), cfg)
    assert [s.kind for s in traj.steps] == ["request", "request"]
    # with the compaction skipped, the gap spans the whole summary + think time
    assert traj.steps[1].gap_before_ms == 35 + 12_000 + 1 + 5_000 + 1 + 5


def test_synthesize_compaction_payload_budget() -> None:
    prev = {"model": "m", "messages": [SYS, U0, A0, T0, A1, U1], "tools": [1], "stream": True}
    total_chars = len(json.dumps(prev["messages"], ensure_ascii=False))
    prev_tokens = total_chars // 4
    body, est = synthesize_compaction_payload(prev, prev_tokens, target_input_tokens=prev_tokens // 3)
    assert "tools" not in body and body["stream"] is True
    assert body["messages"][0] == SYS and body["messages"][-1]["content"] == COMPACTION_INSTRUCTION
    assert 1 <= len(body["messages"]) - 1 < 6
    assert 0 < est <= prev_tokens // 3 + prev_tokens // 6  # within one message of the budget


def test_output_mode_fixed() -> None:
    cfg = Config(name="t", replay=ReplayConfig(output_mode="fixed", output_tokens=77))
    body, _ = normalize_payload(ZAI_PAYLOAD, cfg, max_tokens=5)
    assert body["max_tokens"] == 5  # normalize takes what it is given; the mode is applied by the caller


def test_load_trajectories_order_limit_and_skips(tmp_path: Path) -> None:
    d = tmp_path / "traces"
    d.mkdir()
    build_two_run_trace("a").write(d / "a.jsonl")
    build_two_run_trace("b").write(d / "b.jsonl")
    (d / "c.jsonl").write_text("garbage\n")
    empty = TraceBuilder()
    empty.header(session_id="e")
    empty.shutdown(0, 0, 0)
    empty.write(d / "e.jsonl")

    cfg = Config(name="t", traces=TracesConfig(dir=str(d)))
    rep = load_trajectories(cfg, tmp_path)
    assert [t.session_id for t in rep.trajectories] == ["a", "b"]
    assert (
        len(rep.skipped) == 2
        and any("c.jsonl" in s for s in rep.skipped)
        and any("e.jsonl" in s for s in rep.skipped)
    )

    cfg = Config(
        name="t", traces=TracesConfig(dir=str(d), order="shuffle", limit=1), replay=ReplayConfig(seed=1)
    )
    rep = load_trajectories(cfg, tmp_path)
    assert len(rep.trajectories) == 1

    cfg = Config(name="t", traces=TracesConfig(dir=str(d), include="a.*"))
    assert [t.session_id for t in load_trajectories(cfg, tmp_path).trajectories] == ["a"]

    # relative dir resolves against root
    cfg = Config(name="t", traces=TracesConfig(dir="traces"))
    assert len(load_trajectories(cfg, tmp_path).trajectories) == 2
