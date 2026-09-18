"""Structured JSON-lines logging (CLAUDE.md §10: no print)."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class Logger:
    """Thin wrapper so call sites can pass structured fields as kwargs."""

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    def _emit(self, level: int, msg: str, **fields: Any) -> None:
        self._log.log(level, msg, extra={"fields": fields})

    def info(self, msg: str, **fields: Any) -> None:
        self._emit(logging.INFO, msg, **fields)

    def warning(self, msg: str, **fields: Any) -> None:
        self._emit(logging.WARNING, msg, **fields)

    def error(self, msg: str, **fields: Any) -> None:
        self._emit(logging.ERROR, msg, **fields)


def configure(level: int = logging.INFO) -> None:
    """Route the root logger to stderr as JSON lines. Idempotent."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, _JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> Logger:
    return Logger(name)
