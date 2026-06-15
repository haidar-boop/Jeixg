"""Structured logging setup.

Provides console + rotating-file handlers and an optional JSON formatter so the
same logs can feed a human in development and a log aggregator in production.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON for machine ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach any structured "extra" fields.
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


_STD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


def setup_logging(level: str = "INFO", log_dir: str | Path = "logs",
                  json_logs: bool = False) -> None:
    """Configure root logging. Idempotent across repeated calls."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    if json_logs:
        fmt: logging.Formatter = JsonFormatter()
    else:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    log_path = Path(log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "quanttrade.log", maxBytes=10 * 1024 * 1024, backupCount=5,
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:  # pragma: no cover - read-only fs fallback
        root.warning("Could not create log directory %s; console only", log_path)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger, configuring logging lazily if needed."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
