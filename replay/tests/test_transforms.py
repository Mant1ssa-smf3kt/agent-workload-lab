import copy
from pathlib import Path
from typing import Any

import pytest

from analysis.tests.conftest import A0, A1, SYS, T0, U0, U1
from replay.config import Config, ConfigError, TracesConfig, TransformConfig
from replay.trajectory import Recorded, Step, load_trajectories
from replay.transforms import (
    TRANSFORMS,
    apply_transform,
    system_timestamp,
    tools_rotate,
    truncate_tool_results,
)

REC = Recorded(None, None, None, None, None, None)
TOOLS = [{"type": "function", "function": {"name": n}} for n in ("read", "bash", "edit", "write")]


def long_tool(i: int) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": f"c{i}", "content": f"result-{i}-" + "x" * 2000}


def make_steps(n: int = 6) -> list[Step]:
    """Step k carries a history with k tool results (growing, append-only)."""
    steps = []
    for k in range(n):
        msgs: list[dict[str, Any]] = [SYS, U0]
        for i in range(k):
            msgs += [A0, long_tool(i)]
        msgs.append(U1)
        steps.append(
            Step(
                "t",
                k,
                "request",
                0,
                k,
                k,
                0,
                {"model": "m", "messages": copy.deepcopy(msgs), "tools": copy.deepcopy(TOOLS)},
                REC,
            )
        )
    return steps


def test_identity_returns_equal_steps() -> None:
    steps = make_steps(3)
    out = apply_transform("identity", {}, steps)
    assert out == steps and out is not steps


def test_unknown_transform() -> None:
    with pytest.raises(ValueError, match="unknown transform"):
        apply_transform("nope", {}, make_steps(1))


def test_system_timestamp_differs_per_step_and_is_deterministic() -> None:
    steps = make_steps(3)
    out = system_timestamp(steps, {})
    sys_msgs = [s.payload["messages"][0]["content"] for s in out]
    assert all(c.startswith(SYS["content"]) and "Current time: " in c for c in sys_msgs)
    assert len(set(sys_msgs)) == 3  # every request differs
    assert [s.payload["messages"][1:] for s in out] == [
        s.payload["messages"][1:] for s in steps
    ]  # rest untouched
    assert system_timestamp(steps, {}) == out  # deterministic
    # start position puts it before the system text
    front = system_timestamp(steps, {"position": "start"})[0].payload["messages"][0]["content"]
    assert front.startswith("Current time: ") and front.endswith(SYS["content"])
    # inputs not mutated
    assert steps[0].payload["messages"][0] == SYS


def test_system_timestamp_without_system_message_inserts_one() -> None:
    s = Step("t", 0, "request", 0, 0, 0, 0, {"messages": [U0]}, REC)
    out = system_timestamp([s], {})
    assert out[0].payload["messages"][0]["role"] == "system" and out[0].payload["messages"][1] == U0


def test_tools_rotate_keeps_set_changes_order() -> None:
    steps = make_steps(5)
    out = tools_rotate(steps, {})
    names = [[t["function"]["name"] for t in s.payload["tools"]] for s in out]
    assert names[0] == ["read", "bash", "edit", "write"]
    assert names[1] == ["bash", "edit", "write", "read"]
    assert names[4] == names[0]  # period = len(tools)
    assert all(sorted(n) == sorted(names[0]) for n in names)
    assert [s.payload["messages"] for s in out] == [s.payload["messages"] for s in steps]
    every2 = tools_rotate(steps, {"every": 2})
    assert [t["function"]["name"] for t in every2[1].payload["tools"]] == names[0]
    assert [t["function"]["name"] for t in every2[2].payload["tools"]] == names[1]
    assert steps[1].payload["tools"] == TOOLS  # not mutated


def test_truncate_tool_results_sliding_window() -> None:
    steps = make_steps(6)  # step 5 has tool results 0..4
    out = truncate_tool_results(steps, {"keep_recent": 2, "max_chars": 10})
    tools5 = [m for m in out[5].payload["messages"] if m["role"] == "tool"]
    assert [len(m["content"]) > 40 for m in tools5] == [False, False, False, True, True]
    assert tools5[0]["content"].startswith("result-0-x") and tools5[0]["content"].endswith(
        "…[truncated by harness]"
    )
    # step 4 (tool results 0..3): only 0,1 truncated; step 3: only 0 → the window slides
    tools4 = [m for m in out[4].payload["messages"] if m["role"] == "tool"]
    assert [len(m["content"]) > 40 for m in tools4] == [False, False, True, True]
    # what step 4 kept intact (tool 2), step 5 truncated → shared prefix breaks at tool 2
    assert tools4[2]["content"] != tools5[2]["content"]
    # short results are left alone; inputs not mutated
    short = Step(
        "t",
        0,
        "request",
        0,
        0,
        0,
        0,
        {"messages": [SYS, {"role": "tool", "content": "ok"}, {"role": "tool", "content": "ok2"}]},
        REC,
    )
    assert (
        truncate_tool_results([short], {"keep_recent": 0, "max_chars": 10})[0].payload["messages"][1][
            "content"
        ]
        == "ok"
    )
    assert len(steps[5].payload["messages"][3]["content"]) > 2000


def test_truncate_handles_block_content() -> None:
    s = Step(
        "t",
        0,
        "request",
        0,
        0,
        0,
        0,
        {
            "messages": [
                {
                    "role": "tool",
                    "content": [{"type": "text", "text": "y" * 100}, {"type": "text", "text": "z"}],
                }
            ]
        },
        REC,
    )
    out = truncate_tool_results([s], {"keep_recent": 0, "max_chars": 5, "marker": "!"})
    assert out[0].payload["messages"][0]["content"] == "yyyyy!"


def test_load_trajectories_applies_transform_and_rejects_unknown(traces_dir: Path) -> None:
    cfg = Config(
        name="t", traces=TracesConfig(dir=str(traces_dir)), transform=TransformConfig(name="tools_rotate")
    )
    rep = load_trajectories(cfg, traces_dir)
    t = rep.trajectories[0]
    n0 = [x["function"]["name"] for x in t.steps[0].payload["tools"]]
    n1 = [x["function"]["name"] for x in t.steps[1].payload["tools"]]
    assert n0 != n1 and sorted(n0) == sorted(n1)
    bad = Config(name="t", traces=TracesConfig(dir=str(traces_dir)), transform=TransformConfig(name="bogus"))
    with pytest.raises(ConfigError, match=r"transform\.name"):
        load_trajectories(bad, traces_dir)


def test_registry_names() -> None:
    assert set(TRANSFORMS) == {"identity", "system_timestamp", "tools_rotate", "truncate_tool_results"}
    assert SYS and U0 and A0 and T0 and A1 and U1  # fixtures imported for shape parity
