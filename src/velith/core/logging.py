"""Structured logging foundation for Velith.

Observability is a first-class deliverable from the first commit (D9 / M0 §9).
This module is the *single* place logging is configured. Every other module
obtains a logger through :func:`get_logger` and never configures logging on its
own. Diagnostic output goes through this logger, never ``print``.

M0 scope is deliberately the foundation only: structured, machine-parseable
records that emit. Trace correlation, episode logging, and provenance fields are
not built here — they arrive with the episode store (M3).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from velith.core.config import LogFormat, Settings, get_settings

# LogRecord attributes that are part of the record machinery rather than
# caller-supplied structured context. Everything *not* in this set (passed via
# ``logger.info(..., extra={...})``) is emitted as structured key/value data.
_RESERVED_RECORD_KEYS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
        "message",
    }
)

# Module-level guard so logging is configured exactly once (M0 §9). This is a
# one-way latch, not mutable application state.
_configured: bool = False


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info is not None:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _build_handler(log_format: LogFormat) -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            )
        )
    return handler


def configure_logging(settings: Settings | None = None) -> None:
    """Configure process-wide logging exactly once.

    Idempotent: repeated calls are no-ops, so importing modules cannot
    accidentally reconfigure logging. Pass ``settings`` explicitly in tests;
    otherwise the validated process settings are used.
    """
    global _configured
    if _configured:
        return
    resolved = settings if settings is not None else get_settings()
    handler = _build_handler(resolved.log_format)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(resolved.log_level)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger.

    The single sanctioned accessor for loggers in Velith. Ensures logging is
    configured (lazily, once) before returning the named logger.
    """
    if not _configured:
        configure_logging()
    return logging.getLogger(name)
