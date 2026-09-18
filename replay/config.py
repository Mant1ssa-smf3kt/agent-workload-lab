"""Experiment config schema (CLAUDE.md §10: every tunable lives here, in YAML, nothing hard-coded).

    experiments/<name>/config.yaml  →  load_config()  →  Config

Every field has a default so a minimal config is just ``name:``; the resolved
config is written next to the artifact so a run is reproducible from it alone.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TracesConfig:
    dir: str = "traces"
    """Directory searched recursively, or a single file."""
    include: str = "*.jsonl"
    """Glob (on file name) applied within ``dir``."""
    min_requests: int = 1
    """Traces with fewer requests are skipped (an opened-and-quit session)."""
    order: Literal["sorted", "shuffle"] = "sorted"
    """Trajectory dispatch order; ``shuffle`` uses ``replay.seed``."""
    limit: int | None = None
    """Take only the first N trajectories after ordering."""


@dataclass(frozen=True)
class ServerConfig:
    base_url: str = "http://127.0.0.1:30000/v1"
    model: str = "Qwen/Qwen3-8B-FP8"
    """``model`` field sent to the server; must match ``--served-model-name``."""
    api_key: str = "sglang"
    metrics_url: str | None = "http://127.0.0.1:30000/metrics"
    """Prometheus endpoint (``--enable-metrics``). ``null`` disables scraping."""
    timeout_s: float = 600.0
    extra_body: dict[str, Any] = field(
        default_factory=lambda: {"chat_template_kwargs": {"enable_thinking": False}}
    )
    """Merged into every request body after normalization (e.g. Qwen3 thinking switch)."""


@dataclass(frozen=True)
class ReplayConfig:
    concurrency: int = 1
    """Trajectories in flight simultaneously. Requests within one trajectory are sequential."""
    timing: Literal["real", "compressed"] = "real"
    """real: honour recorded gaps between requests (tool time + human think time).
    compressed: no gaps — next request goes out as soon as the previous ends.
    Numbers from the two modes are not comparable (CLAUDE.md §4)."""
    gap_scale: float = 1.0
    """Multiplier on recorded gaps (real only)."""
    max_gap_s: float = 60.0
    """Cap on any single gap (real only); bounds human think time."""
    seed: int = 0
    output_mode: Literal["recorded", "fixed"] = "recorded"
    """recorded: max_tokens = recorded output tokens; fixed: max_tokens = output_tokens."""
    output_tokens: int = 256
    ignore_eos: bool = True
    """Ask the server to decode exactly max_tokens so output length is faithful to the recording,
    independent of what the small model would have said."""
    temperature: float = 0.0
    compaction: Literal["synthesize", "skip"] = "synthesize"
    """The compaction summary call bypasses pi's request hook (docs/later.md); we only know its
    size. synthesize: send a request of the recorded size, marked synthetic. skip: drop it."""
    stream: bool = True
    warmup_requests: int = 0
    """Requests sent (and discarded) before measurement starts, from the first trajectory."""


@dataclass(frozen=True)
class TransformConfig:
    """W3: context-assembly strategy applied to each trajectory's payload sequence before replay.
    ``identity`` replays exactly what pi sent. Others live in replay/transforms.py."""

    name: str = "identity"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    name: str
    traces: TracesConfig = field(default_factory=TracesConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    replay: ReplayConfig = field(default_factory=ReplayConfig)
    transform: TransformConfig = field(default_factory=TransformConfig)
    fingerprint: str | None = None
    """Path to the serve fingerprint JSON written by scripts/serve.sh (serve-latest.json).
    Required for a real run (CLAUDE.md §9); ignored in dry-run."""
    out: str | None = None
    """Artifact root; default experiments/<name>/out (resolved relative to the config file's dir)."""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build(cls: type[Any], data: dict[str, Any], path: str) -> Any:
    fields = {f.name: f for f in cls.__dataclass_fields__.values()}
    unknown = set(data) - set(fields)
    if unknown:
        raise ConfigError(f"{path}: unknown keys {sorted(unknown)} (known: {sorted(fields)})")
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        nested = _NESTED.get((cls, key))
        if nested is not None:
            if not isinstance(value, dict):
                raise ConfigError(f"{path}.{key}: expected a mapping")
            kwargs[key] = _build(nested, value, f"{path}.{key}")
        else:
            kwargs[key] = value
    return cls(**kwargs)


_NESTED: dict[tuple[type[Any], str], type[Any]] = {
    (Config, "traces"): TracesConfig,
    (Config, "server"): ServerConfig,
    (Config, "replay"): ReplayConfig,
    (Config, "transform"): TransformConfig,
}


def validate(cfg: Config) -> None:
    r = cfg.replay
    if not cfg.name or "/" in cfg.name:
        raise ConfigError("name must be a non-empty directory-safe string")
    if r.concurrency < 1:
        raise ConfigError("replay.concurrency must be >= 1")
    if r.timing not in ("real", "compressed"):
        raise ConfigError("replay.timing must be 'real' or 'compressed'")
    if r.gap_scale < 0 or r.max_gap_s < 0:
        raise ConfigError("replay.gap_scale and max_gap_s must be >= 0")
    if r.output_mode not in ("recorded", "fixed"):
        raise ConfigError("replay.output_mode must be 'recorded' or 'fixed'")
    if r.output_tokens < 1:
        raise ConfigError("replay.output_tokens must be >= 1")
    if r.compaction not in ("synthesize", "skip"):
        raise ConfigError("replay.compaction must be 'synthesize' or 'skip'")
    if cfg.traces.order not in ("sorted", "shuffle"):
        raise ConfigError("traces.order must be 'sorted' or 'shuffle'")
    if cfg.traces.min_requests < 0:
        raise ConfigError("traces.min_requests must be >= 0")
    if cfg.server.timeout_s <= 0:
        raise ConfigError("server.timeout_s must be > 0")


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    if "name" not in raw:
        raw = {"name": path.parent.name, **raw}
    cfg: Config = _build(Config, raw, "config")
    validate(cfg)
    return cfg


def resolve_out_dir(cfg: Config, config_path: Path) -> Path:
    if cfg.out:
        return Path(cfg.out).expanduser()
    return config_path.parent / "out"
