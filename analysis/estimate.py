"""First gate, no GPU (docs/findings.md §6): single-tenant radix-cache hit-rate estimate for an
experiment config.

Every step the replayer would send — same loader, normalization, transform and dispatch order as
``replay.run`` — is rendered through the served model's *real* chat template and tokenizer the way
SGLang's OpenAI endpoint does it (``serving_chat.py``: ``apply_chat_template(tokenize=False,
add_generation_prompt=True, tools=…)`` then ``encode(add_special_tokens=False)``; list content
flattened to ``" ".join(text parts)``). Its cached prefix is taken as the token-level longest common
prefix with what the server has already seen: the previous step of the same trajectory, or the
first step of an earlier trajectory (the shared system prompt). No eviction, no concurrency —
this is the c=1 / infinite-cache limit. It says nothing about TTFT or latency, and nothing about
concurrency > 1; that is the second gate (GPU).

    just estimate EXP [AGAINST]   →  experiments/EXP/estimate.json + estimate.md

Calibration against measured runs: docs/decisions.md 2026-09-21 (identity 0.9631 vs 0.9633,
system_timestamp 0.1061 vs 0.1059, the timestamp's prompt-token delta exact).

Tokenizer files (``tokenizer.json`` + ``tokenizer_config.json``) are pulled from ModelScope into
``~/.cache/agent-workload-lab/tokenizers/<model>/`` on first use (CLAUDE.md §6: weights via
ModelScope; 11 MB, never committed). ``--tokenizer-dir`` / ``$AWL_TOKENIZER_DIR`` point at an
existing model directory instead (e.g. the served model's on the remote).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment
from tokenizers import Tokenizer

from analysis.log import configure, get_logger
from analysis.report import config_diff
from analysis.stats import Pct, pct
from replay.artifact import git_info, sha256_file, sha256_json
from replay.config import Config, load_config
from replay.trajectory import Trajectory, load_trajectories

log = get_logger("analysis.estimate")
REPO_ROOT = Path(__file__).resolve().parents[1]

TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json")
MODELSCOPE_URL = "https://www.modelscope.cn/models/{model}/resolve/master/{file}"
DEFAULT_CACHE = Path("~/.cache/agent-workload-lab/tokenizers").expanduser()
TOKENIZER_DIR_ENV = "AWL_TOKENIZER_DIR"


# ── tokenizer bundle ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenizerBundle:
    model: str
    dir: Path
    tokenizer: Tokenizer
    chat_template: str
    meta: dict[str, Any]
    """Provenance: file sha256s, where they came from."""


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "agent-workload-lab"})
    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)
    tmp.replace(dest)


def load_tokenizer(
    model: str,
    dir_: Path | None = None,
    *,
    cache_dir: Path = DEFAULT_CACHE,
    download: bool = True,
    url_template: str = MODELSCOPE_URL,
) -> TokenizerBundle:
    """``dir_`` (or ``$AWL_TOKENIZER_DIR``) must already hold the files; otherwise they are looked
    up in ``cache_dir/<model>/`` and fetched from ModelScope when missing and ``download``."""
    env_dir = os.environ.get(TOKENIZER_DIR_ENV)
    if dir_ is None and env_dir:
        dir_ = Path(env_dir).expanduser()
    explicit = dir_ is not None
    d = dir_ if dir_ is not None else cache_dir / model
    source = "dir" if explicit else "cache"
    for name in TOKENIZER_FILES:
        p = d / name
        if p.exists():
            continue
        if explicit or not download:
            raise FileNotFoundError(f"{p} missing (model {model}); pass --tokenizer-dir or allow download")
        url = url_template.format(model=model, file=name)
        log.info("fetching tokenizer file", url=url, dest=str(p))
        _download(url, p)
        source = "modelscope"
    cfg = json.loads((d / "tokenizer_config.json").read_text(encoding="utf-8"))
    template = cfg.get("chat_template")
    if not isinstance(template, str):
        raise ValueError(f"{d / 'tokenizer_config.json'}: no string chat_template")
    meta = {
        "model": model,
        "dir": str(d),
        "source": source,
        "files": {name: sha256_file(d / name) for name in TOKENIZER_FILES},
        "chat_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
    }
    return TokenizerBundle(model, d, Tokenizer.from_file(str(d / "tokenizer.json")), template, meta)


# ── rendering (what SGLang's /v1/chat/completions feeds the model) ────────


def _tojson(
    x: Any,
    ensure_ascii: bool = False,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
    sort_keys: bool = False,
) -> str:
    # transformers' chat-template ``tojson`` (not jinja2's HTML-escaping default).
    return json.dumps(x, ensure_ascii=ensure_ascii, indent=indent, separators=separators, sort_keys=sort_keys)


def _raise(msg: str) -> None:
    raise TemplateError(msg)


def sglang_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``process_content_for_template_format(msg, "string", …)``: text-only templates get list
    content flattened to the text parts joined by a space; ``None``-valued keys are dropped."""
    out: list[dict[str, Any]] = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            parts = [p["text"] for p in c if isinstance(p, dict) and p.get("type") in ("text", "input_text")]
            m = {**m, "content": " ".join(parts) if parts else ""}
        out.append({k: v for k, v in m.items() if v is not None})
    return out


class Renderer:
    def __init__(self, chat_template: str, tokenizer: Tokenizer, template_kwargs: dict[str, Any]) -> None:
        env = ImmutableSandboxedEnvironment(
            trim_blocks=True, lstrip_blocks=True, extensions=["jinja2.ext.loopcontrols"]
        )
        env.filters["tojson"] = _tojson
        env.globals["raise_exception"] = _raise
        env.globals["strftime_now"] = lambda fmt: time.strftime(fmt)
        self.template = env.from_string(chat_template)
        self.tokenizer = tokenizer
        self.kwargs = dict(template_kwargs)

    def render(self, payload: dict[str, Any]) -> str:
        tools = payload.get("tools")
        return self.template.render(
            messages=sglang_messages(list(payload.get("messages") or [])),
            tools=tools if tools else None,
            add_generation_prompt=True,
            **self.kwargs,
        )

    def encode(self, payload: dict[str, Any]) -> list[int]:
        ids: list[int] = self.tokenizer.encode(self.render(payload), add_special_tokens=False).ids
        return ids


# ── prefix match ──────────────────────────────────────────────────────────


def lcp(a: Sequence[int], b: Sequence[int]) -> int:
    """Length of the longest common prefix. Binary search over slice equality (C speed)."""
    n = min(len(a), len(b))
    if n == 0 or a[0] != b[0]:
        return 0
    lo, hi = 1, n  # invariant: a[:lo] == b[:lo]
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a[:mid] == b[:mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


@dataclass(frozen=True)
class StepEstimate:
    trajectory: str
    idx: int
    kind: str
    synthetic: bool
    warmup: bool
    prompt_tokens: int
    cached_tokens: int
    """Match against the previous step of the trajectory (or an earlier trajectory's first step)."""
    cached_tokens_any: int
    """Match against *any* earlier step of the trajectory: the infinite-cache upper bound."""

    @property
    def hit(self) -> float:
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0

    @property
    def hit_any(self) -> float:
        return self.cached_tokens_any / self.prompt_tokens if self.prompt_tokens else 0.0


def estimate_steps(
    trajectories: list[Trajectory], renderer: Renderer, warmup_requests: int
) -> list[StepEstimate]:
    """Two numbers per step. ``cached_tokens``: longest match against the previous step of its
    trajectory or the first step of any earlier trajectory — the branch that certainly survives at
    c=1; calibrated (docs/decisions.md 2026-09-21). ``cached_tokens_any``: also against every
    earlier step of the trajectory — what an infinitely large cache would give; a rewrite with a
    period (tools_rotate) re-matches an older branch, and the measured value lies between the
    two because the pool cannot keep every branch. Mirrors ``replay.scheduler``: warmup = the
    first N steps of the first trajectory. A byte-identical resend still prefills one token."""
    first_prompts: list[list[int]] = []  # first step of each *earlier* trajectory
    out: list[StepEstimate] = []
    for ti, traj in enumerate(trajectories):
        history: list[list[int]] = []
        for step in traj.steps:
            ids = renderer.encode(step.payload)
            cap = max(0, len(ids) - 1)
            shared = max((lcp(c, ids) for c in first_prompts), default=0)
            recent = max(shared, lcp(history[-1], ids)) if history else shared
            older = max((lcp(h, ids) for h in history[:-1]), default=0)
            out.append(
                StepEstimate(
                    trajectory=traj.id,
                    idx=step.idx,
                    kind=step.kind,
                    synthetic=step.synthetic,
                    warmup=ti == 0 and step.idx < warmup_requests,
                    prompt_tokens=len(ids),
                    cached_tokens=min(recent, cap),
                    cached_tokens_any=min(max(recent, older), cap),
                )
            )
            history.append(ids)
        if history:
            first_prompts.append(history[0])
    return out


def _agg(rs: list[StepEstimate]) -> dict[str, Any]:
    prompt = sum(r.prompt_tokens for r in rs)
    cached = sum(r.cached_tokens for r in rs)
    cached_any = sum(r.cached_tokens_any for r in rs)
    hits: Pct = pct(r.hit for r in rs)
    return {
        "n": len(rs),
        "prompt_tokens_total": prompt,
        "cached_tokens_total": cached,
        "cache_hit_rate": cached / prompt if prompt else None,  # §5: Σcached / Σprompt, per request
        "cache_hit_per_request": hits,
        "frac_below_half": (sum(1 for r in rs if r.hit < 0.5) / len(rs)) if rs else None,
        "cached_tokens_total_any": cached_any,
        "cache_hit_rate_infinite_cache": cached_any / prompt if prompt else None,
    }


def aggregate(steps: list[StepEstimate]) -> dict[str, Any]:
    measured = [s for s in steps if not s.warmup]
    per_traj = {
        tid: _agg([s for s in measured if s.trajectory == tid])
        for tid in sorted({s.trajectory for s in measured})
    }
    return {
        "n_steps": len(steps),
        "n_warmup": len(steps) - len(measured),
        "n_synthetic": sum(1 for s in measured if s.synthetic),
        "all": _agg(measured),
        "excluding_synthetic": _agg([s for s in measured if not s.synthetic]),
        "per_trajectory": per_traj,
    }


# ── one experiment ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Estimate:
    name: str
    config_path: Path
    cfg: Config
    result: dict[str, Any]
    traces: list[dict[str, Any]]
    skipped: list[str]


def estimate_config(config_path: Path, bundle: TokenizerBundle, root: Path = REPO_ROOT) -> Estimate:
    cfg = load_config(config_path)
    if cfg.server.model != bundle.model:
        log.warning("tokenizer model differs from config", tokenizer=bundle.model, config=cfg.server.model)
    report = load_trajectories(cfg, root)
    for s in report.skipped:
        log.warning("skipped trace", reason=s)
    kwargs = cfg.server.extra_body.get("chat_template_kwargs") or {}
    renderer = Renderer(bundle.chat_template, bundle.tokenizer, dict(kwargs))
    t0 = time.monotonic()
    steps = estimate_steps(report.trajectories, renderer, cfg.replay.warmup_requests)
    result = aggregate(steps)
    log.info(
        "estimated",
        experiment=cfg.name,
        steps=len(steps),
        cache_hit_rate=result["all"]["cache_hit_rate"],
        seconds=round(time.monotonic() - t0, 1),
    )
    traces = [
        {"id": t.id, "sha256": sha256_file(t.path), "steps": len(t.steps), "synthetic": t.n_synthetic}
        for t in report.trajectories
    ]
    return Estimate(cfg.name, config_path, cfg, result, traces, report.skipped)


def _mtok(v: float | None) -> str:
    return "—" if v is None else f"{v / 1e6:.2f}M"


def _hit(v: float | None) -> str:
    return "—" if v is None else f"{v:.4f}"


def _pct_row(p: Pct) -> str:
    return " / ".join("—" if v is None else f"{v:.3f}" for v in (p["p50"], p["p95"], p["p99"]))


def _frac(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def _row(label: str, a: dict[str, Any]) -> str:
    return (
        f"| {label} | {_hit(a['cache_hit_rate'])} | {_hit(a['cache_hit_rate_infinite_cache'])} | "
        f"{_pct_row(a['cache_hit_per_request'])} | {_frac(a['frac_below_half'])} | "
        f"{_mtok(a['prompt_tokens_total'])} | {a['n']} |"
    )


def render_markdown(
    est: Estimate, bundle: TokenizerBundle, against: Estimate | None, git: dict[str, Any]
) -> str:
    cfg = est.cfg
    r = est.result
    kwargs = cfg.server.extra_body.get("chat_template_kwargs") or {}
    L: list[str] = [f"# {est.name} · 第一道门估计（单租户、无驱逐、不含延迟）", ""]
    L.append(
        f"模型 / tokenizer：{bundle.model}（tokenizer.json {bundle.meta['files']['tokenizer.json'][:12]}… · "
        f"chat_template {bundle.meta['chat_template_sha256'][:12]}… · chat_template_kwargs "
        f"{json.dumps(kwargs, ensure_ascii=False)}）· traces {len(est.traces)} · steps {r['n_steps']}"
        f"（合成 {r['n_synthetic']}，warmup {r['n_warmup']} 不计）· transform {cfg.transform.name} "
        f"{json.dumps(cfg.transform.params, ensure_ascii=False)} · "
        f"analysis commit {(git.get('commit') or 'TBD')[:8]}" + ("（dirty）" if git.get("dirty") else "")
    )
    if cfg.replay.concurrency > 1:
        L.append("")
        L.append(
            f"> config 的 concurrency={cfg.replay.concurrency}；本估计按 c=1、不驱逐算，"
            "并发下的驱逐与排队只能上 GPU（docs/findings.md §6）。"
        )
    L.append("")
    L.append(
        "| 组 | cache hit（估计） | 上界（缓存无限） | 每请求命中 P50 / P95 / P99 | 命中 < 0.5 的请求 | "
        "prompt tok 总 | n |"
    )
    L.append("|---|---|---|---|---|---|---|")
    L.append(_row(est.name, r["all"]))
    if r["n_synthetic"]:
        L.append(_row(f"{est.name}（不含合成）", r["excluding_synthetic"]))
    if against is not None:
        b = against.result
        L.append(_row(f"{against.name}（对照）", b["all"]))
        ha, hb = r["all"]["cache_hit_rate"], b["all"]["cache_hit_rate"]
        pa, pb = r["all"]["prompt_tokens_total"], b["all"]["prompt_tokens_total"]
        if ha is not None and hb is not None:
            rel = f" ({(ha - hb) / hb * 100:+.1f}%)" if hb else ""
            L.append(f"| Δ（{est.name} − {against.name}） | {ha - hb:+.4f}{rel} | | | | {pa - pb:+,} | |")
        diffs = config_diff(cfg.to_dict(), against.cfg.to_dict())
        L.append("")
        L.append("配置差异：" + ("（无）" if not diffs else ""))
        L.extend(
            f"- `{k}`: {json.dumps(va, ensure_ascii=False)} → {json.dumps(vb, ensure_ascii=False)}"
            for k, va, vb in diffs
        )
        if len(diffs) > 1:
            L.append("")
            L.append(f"> 动了 {len(diffs)} 个变量（CLAUDE.md §9）。")
    L.append("")
    L.append(
        "估计口径：每个请求的命中 token = 经服务端 chat template 渲染、真 tokenizer 分词后，"
        "与「同一轨迹的上一请求」或「更早轨迹的首请求」的最长公共前缀（c=1 派发顺序、不驱逐）；"
        "命中率 = Σ命中 / Σprompt（§5）。「上界」另把同一轨迹全部更早请求算作候选（缓存无限大）；"
        "有周期的改写（tools_rotate）实测落在两者之间。不估计 TTFT / 单轮延迟。"
        "校准与适用边界见 docs/decisions.md 2026-09-21。"
    )
    if est.skipped:
        L.append("")
        L.append("跳过的 trace：")
        L.extend(f"- {s}" for s in est.skipped)
    return "\n".join(L) + "\n"


def to_json(
    est: Estimate, bundle: TokenizerBundle, against: Estimate | None, git: dict[str, Any]
) -> dict[str, Any]:
    cfg = est.cfg
    d: dict[str, Any] = {
        "experiment": est.name,
        "config_path": str(est.config_path),
        "config_sha256": sha256_json(cfg.to_dict()),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "analysis_git": git,
        "python": sys.version.split()[0],
        "tokenizer": bundle.meta,
        "chat_template_kwargs": cfg.server.extra_body.get("chat_template_kwargs") or {},
        "assumptions": {
            "concurrency": 1,
            "eviction": "none",
            "candidates": "previous step of the same trajectory, first step of earlier trajectories",
            "note": "single-tenant token-LCP estimate; no TTFT/latency; concurrency effects need GPU",
        },
        "config": {
            "concurrency": cfg.replay.concurrency,
            "timing": cfg.replay.timing,
            "transform": {"name": cfg.transform.name, "params": cfg.transform.params},
            "traces": {"order": cfg.traces.order, "limit": cfg.traces.limit, "include": cfg.traces.include},
            "warmup_requests": cfg.replay.warmup_requests,
            "compaction": cfg.replay.compaction,
        },
        "traces": est.traces,
        "skipped": est.skipped,
        "estimate": est.result,
    }
    if against is not None:
        ha, hb = est.result["all"]["cache_hit_rate"], against.result["all"]["cache_hit_rate"]
        d["against"] = {
            "experiment": against.name,
            "config_sha256": sha256_json(against.cfg.to_dict()),
            "cache_hit_rate": hb,
            "delta": None if ha is None or hb is None else ha - hb,
            "config_diff": [list(x) for x in config_diff(cfg.to_dict(), against.cfg.to_dict())],
            "estimate": {
                k: against.result[k] for k in ("all", "excluding_synthetic", "n_steps", "n_synthetic")
            },
        }
    return d


# ── CLI ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path, help="experiments/<name>/config.yaml")
    ap.add_argument(
        "--against", type=Path, help="control experiment's config.yaml (adds a Δ row + config diff)"
    )
    ap.add_argument("--tokenizer-dir", type=Path, help=f"directory holding {' + '.join(TOKENIZER_FILES)}")
    ap.add_argument("--no-download", action="store_true", help="fail instead of fetching tokenizer files")
    ap.add_argument(
        "--out-dir", type=Path, help="where estimate.json / estimate.md go (default: next to config)"
    )
    args = ap.parse_args(argv)
    configure()
    cfg = load_config(args.config)
    bundle = load_tokenizer(cfg.server.model, args.tokenizer_dir, download=not args.no_download)
    est = estimate_config(args.config, bundle)
    against = estimate_config(args.against, bundle) if args.against else None
    git = git_info(REPO_ROOT)
    out = args.out_dir or args.config.parent
    out.mkdir(parents=True, exist_ok=True)
    (out / "estimate.json").write_text(
        json.dumps(to_json(est, bundle, against, git), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "estimate.md").write_text(render_markdown(est, bundle, against, git), encoding="utf-8")
    log.info("wrote estimate", out=str(out), cache_hit_rate=est.result["all"]["cache_hit_rate"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
