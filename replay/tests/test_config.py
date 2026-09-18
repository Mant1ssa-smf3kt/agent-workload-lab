from pathlib import Path

import pytest

from replay.config import Config, ConfigError, load_config, resolve_out_dir


def write(tmp_path: Path, text: str) -> Path:
    d = tmp_path / "exp-a"
    d.mkdir(exist_ok=True)
    p = d / "config.yaml"
    p.write_text(text)
    return p


def test_minimal_config_uses_dir_name_and_defaults(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, ""))
    assert cfg.name == "exp-a"
    assert cfg.replay.concurrency == 1 and cfg.replay.timing == "real"
    assert cfg.server.model == "Qwen/Qwen3-8B-FP8"
    assert cfg.server.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert cfg.transform.name == "identity"
    assert resolve_out_dir(cfg, tmp_path / "exp-a" / "config.yaml") == tmp_path / "exp-a" / "out"


def test_nested_override_and_out(tmp_path: Path) -> None:
    cfg = load_config(
        write(
            tmp_path,
            "name: c4\nreplay:\n  concurrency: 4\n  timing: compressed\n"
            "server:\n  model: m\n  metrics_url: null\nout: /tmp/x\n",
        )
    )
    assert cfg.name == "c4" and cfg.replay.concurrency == 4 and cfg.replay.timing == "compressed"
    assert cfg.server.model == "m" and cfg.server.metrics_url is None
    assert resolve_out_dir(cfg, tmp_path) == Path("/tmp/x")
    assert isinstance(cfg.to_dict()["replay"], dict)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("bogus: 1\n", "unknown keys"),
        ("replay:\n  concurrencyy: 2\n", "unknown keys"),
        ("replay: 3\n", "expected a mapping"),
        ("replay:\n  concurrency: 0\n", "concurrency"),
        ("replay:\n  timing: fast\n", "timing"),
        ("replay:\n  output_mode: guess\n", "output_mode"),
        ("replay:\n  compaction: drop\n", "compaction"),
        ("traces:\n  order: random\n", "order"),
        ("server:\n  timeout_s: 0\n", "timeout_s"),
        ("name: a/b\n", "directory-safe"),
        ("- 1\n", "mapping"),
    ],
)
def test_invalid(tmp_path: Path, text: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_config(write(tmp_path, text))


def test_config_is_frozen() -> None:
    cfg = Config(name="x")
    with pytest.raises(AttributeError):
        cfg.name = "y"  # type: ignore[misc]
