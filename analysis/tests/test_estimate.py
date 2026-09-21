"""analysis.estimate: the offline first gate. A tiny word-level tokenizer and a one-line template
stand in for the real Qwen3 files so every number below can be checked by hand; nothing touches
the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tokenizers import Regex, Tokenizer, models, pre_tokenizers

from analysis.estimate import (
    Renderer,
    TokenizerBundle,
    aggregate,
    estimate_steps,
    lcp,
    load_tokenizer,
    main,
    sglang_messages,
)
from analysis.tests.conftest import build_two_run_trace
from replay.trajectory import Recorded, Step, Trajectory

WORDS = [
    "[UNK]",
    "system",
    "user",
    "assistant",
    "tool",
    "<gen>",
    "s",
    "u",
    "r0",
    "r1",
    "r2",
    "x",
    "y",
    "tools",
]
TEMPLATE = (
    "{% if tools %}tools {{ tools | tojson }}\n{% endif %}"
    "{% for m in messages %}{{ m.role }} {{ m.content }}\n{% endfor %}"
    "{% if add_generation_prompt %}assistant <gen>{% endif %}"
)
REC = Recorded(None, None, None, None, None, None)


def tiny_tokenizer() -> Tokenizer:
    tok = Tokenizer(models.WordLevel({w: i for i, w in enumerate(WORDS)}, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    return tok


def char_tokenizer() -> Tokenizer:
    """One token per character, so a changing timestamp actually changes the token sequence."""
    chars = [chr(c) for c in range(32, 127)] + ["\n"]
    tok = Tokenizer(models.WordLevel({c: i for i, c in enumerate(["[UNK]", *chars])}, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Split(Regex("[\\s\\S]"), "isolated")
    return tok


def renderer() -> Renderer:
    return Renderer(TEMPLATE, tiny_tokenizer(), {})


def step(traj: str, idx: int, msgs: list[dict[str, Any]], *, synthetic: bool = False) -> Step:
    return Step(
        trajectory=traj,
        idx=idx,
        kind="compaction" if synthetic else "request",
        run=0,
        turn=idx,
        req=idx,
        gap_before_ms=0,
        payload={"messages": msgs},
        recorded=REC,
        synthetic=synthetic,
    )


def traj(tid: str, steps: list[Step]) -> Trajectory:
    return Trajectory(
        id=tid,
        path=Path(tid),
        session_id=tid,
        pi_version="0",
        extension_version="0",
        recorded_model=None,
        steps=steps,
    )


SYS = {"role": "system", "content": "s"}
USER = {"role": "user", "content": "u"}


def tool(i: int) -> dict[str, Any]:
    return {"role": "tool", "content": f"r{i}"}


# ── pieces ────────────────────────────────────────────────────────────────


def test_lcp() -> None:
    assert lcp([], [1]) == 0
    assert lcp([1, 2, 3], [1, 2, 3]) == 3
    assert lcp([1, 2, 3], [1, 2, 4, 5]) == 2
    assert lcp([2], [1, 2]) == 0
    a = list(range(50_000))
    assert lcp(a, [*a[:31_337], -1]) == 31_337


def test_sglang_messages_flatten_and_drop_none() -> None:
    msgs: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "a"}, {"type": "image_url"}, {"type": "text", "text": "b"}],
        },
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
        {"role": "user", "content": [{"type": "image_url"}]},
        {"role": "tool", "content": "kept"},
    ]
    out = sglang_messages(msgs)
    assert out[0] == {"role": "user", "content": "a b"}
    assert out[1] == {"role": "assistant", "tool_calls": [{"id": "1"}]}
    assert out[2] == {"role": "user", "content": ""}
    assert out[3] == {"role": "tool", "content": "kept"}
    assert msgs[1]["content"] is None  # input untouched


def test_renderer_passes_tools_and_generation_prompt() -> None:
    r = renderer()
    text = r.render({"messages": [SYS, USER], "tools": [{"type": "function"}]})
    assert text.startswith("tools ") and text.endswith("assistant <gen>")
    assert r.render({"messages": [SYS], "tools": []}).startswith("system s")  # empty list → no tools block
    assert r.encode({"messages": [SYS, USER]}) == [1, 6, 2, 7, 3, 5]


# ── the estimate ──────────────────────────────────────────────────────────


def test_append_only_history_hits_everything_but_the_new_turn() -> None:
    steps = [
        step("t", 0, [SYS, USER]),  # system s user u assistant <gen>            → 6 tokens
        step("t", 1, [SYS, USER, tool(0)]),  # … tool r0 assistant <gen>         → 8, shares 4
        step("t", 2, [SYS, USER, tool(0), tool(1)]),  # … tool r1 assistant <gen> → 10, shares 6
    ]
    est = estimate_steps([traj("t", steps)], renderer(), warmup_requests=0)
    assert [(e.prompt_tokens, e.cached_tokens) for e in est] == [(6, 0), (8, 4), (10, 6)]
    agg = aggregate(est)
    assert agg["all"]["prompt_tokens_total"] == 24
    assert agg["all"]["cached_tokens_total"] == 10
    assert agg["all"]["cache_hit_rate"] == pytest.approx(10 / 24)
    assert agg["all"]["cache_hit_per_request"]["p50"] == pytest.approx(0.5)
    assert agg["all"]["frac_below_half"] == pytest.approx(1 / 3)  # only step 0


def test_rewriting_the_head_leaves_only_the_untouched_prefix() -> None:
    # Like system_timestamp: the system message differs every request → only "system" matches.
    steps = [
        step("t", 0, [{"role": "system", "content": "x"}, USER]),
        step("t", 1, [{"role": "system", "content": "y"}, USER, tool(0)]),
    ]
    est = estimate_steps([traj("t", steps)], renderer(), warmup_requests=0)
    assert est[1].cached_tokens == 1


def test_periodic_rewrite_rematches_an_older_branch_only_in_the_upper_bound() -> None:
    # Like tools_rotate with period 2: step 2 renders the same head as step 0, so with an infinite
    # cache it matches step 0's whole prompt; the previous-step estimate sees only "system".
    heads = [{"role": "system", "content": "x"}, {"role": "system", "content": "y"}]
    steps = [step("t", k, [heads[k % 2], USER, *[tool(i) for i in range(k)]]) for k in range(3)]
    est = estimate_steps([traj("t", steps)], renderer(), warmup_requests=0)
    assert (est[2].cached_tokens, est[2].cached_tokens_any) == (1, 4)  # "system" vs "system x user u"
    assert est[1].cached_tokens == est[1].cached_tokens_any == 1
    agg = aggregate(est)
    assert agg["all"]["cache_hit_rate"] < agg["all"]["cache_hit_rate_infinite_cache"]


def test_first_step_of_a_later_trajectory_matches_the_shared_system_prompt() -> None:
    a = traj("a", [step("a", 0, [SYS, USER]), step("a", 1, [SYS, USER, tool(0)])])
    b = traj("b", [step("b", 0, [SYS, {"role": "user", "content": "x"}])])
    est = estimate_steps([a, b], renderer(), warmup_requests=0)
    assert est[2].cached_tokens == 3  # "system s user" from a's first step, not a's last step's history


def test_identical_resend_still_prefills_one_token() -> None:
    est = estimate_steps([traj("t", [step("t", 0, [SYS, USER]), step("t", 1, [SYS, USER])])], renderer(), 0)
    assert est[1].cached_tokens == est[1].prompt_tokens - 1


def test_warmup_and_synthetic_accounting() -> None:
    a = traj(
        "a",
        [
            step("a", 0, [SYS, USER]),
            step("a", 1, [SYS, USER, tool(0)]),
            step("a", 2, [SYS, USER, tool(0), tool(1)], synthetic=True),
        ],
    )
    b = traj("b", [step("b", 0, [SYS, USER])])
    agg = aggregate(estimate_steps([a, b], renderer(), warmup_requests=1))
    assert agg["n_steps"] == 4 and agg["n_warmup"] == 1 and agg["n_synthetic"] == 1
    assert agg["all"]["n"] == 3 and agg["excluding_synthetic"]["n"] == 2
    assert set(agg["per_trajectory"]) == {"a", "b"}
    assert agg["per_trajectory"]["a"]["n"] == 2  # warmup step excluded


# ── tokenizer bundle + CLI (offline) ──────────────────────────────────────


def write_bundle(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    char_tokenizer().save(str(d / "tokenizer.json"))
    (d / "tokenizer_config.json").write_text(json.dumps({"chat_template": TEMPLATE}), encoding="utf-8")


def test_load_tokenizer_from_dir_and_offline_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_bundle(tmp_path / "m")
    b = load_tokenizer("fake/m", tmp_path / "m", download=False)
    assert isinstance(b, TokenizerBundle) and b.chat_template == TEMPLATE and b.meta["source"] == "dir"
    assert b.tokenizer.encode("ab\n", add_special_tokens=False).ids == [66, 67, 96]
    assert set(b.meta["files"]) == {"tokenizer.json", "tokenizer_config.json"}
    with pytest.raises(FileNotFoundError):
        load_tokenizer("fake/missing", cache_dir=tmp_path / "cache", download=False)
    monkeypatch.setenv("AWL_TOKENIZER_DIR", str(tmp_path / "m"))
    assert load_tokenizer("fake/m", download=False).meta["source"] == "dir"


def test_main_writes_estimate_and_compare(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    traces.mkdir()
    build_two_run_trace("a").write(traces / "a.jsonl")
    build_two_run_trace("b").write(traces / "b.jsonl")
    write_bundle(tmp_path / "tok")

    def cfg(name: str, transform: str) -> Path:
        d = tmp_path / "experiments" / name
        d.mkdir(parents=True)
        (d / "config.yaml").write_text(
            f"name: {name}\ntraces: {{dir: {traces}}}\nserver: {{model: fake/m}}\n"
            f"replay: {{warmup_requests: 1}}\ntransform: {{name: {transform}}}\n",
            encoding="utf-8",
        )
        return d / "config.yaml"

    exp, ctl = cfg("exp", "system_timestamp"), cfg("ctl", "identity")
    assert (
        main([str(exp), "--against", str(ctl), "--tokenizer-dir", str(tmp_path / "tok"), "--no-download"])
        == 0
    )
    j = json.loads((exp.parent / "estimate.json").read_text(encoding="utf-8"))
    assert j["experiment"] == "exp" and j["against"]["experiment"] == "ctl"
    assert (
        j["estimate"]["n_warmup"] == 1 and j["estimate"]["n_synthetic"] == 0
    )  # fixture compaction has no usage
    assert 0.0 <= j["estimate"]["all"]["cache_hit_rate"] <= 1.0
    assert j["against"]["delta"] < 0  # timestamp in the system prompt can only lose prefix
    assert j["against"]["config_diff"] == [
        ["transform", {"name": "system_timestamp", "params": {}}, {"name": "identity", "params": {}}]
    ]
    assert (
        j["tokenizer"]["files"]["tokenizer.json"] and j["config"]["transform"]["name"] == "system_timestamp"
    )
    md = (exp.parent / "estimate.md").read_text(encoding="utf-8")
    assert "| exp |" in md and "| ctl（对照） |" in md and "`transform`" in md
