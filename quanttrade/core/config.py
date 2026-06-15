"""Layered configuration system.

Precedence (highest wins):
    1. Environment variables (prefix ``QT_``, double-underscore nesting)
    2. ``.env`` file values (loaded into the environment)
    3. YAML config file (``config/config.yaml`` by default)
    4. Built-in defaults

Secrets (API keys, passwords) should *never* live in the YAML file -- they are
read from the environment and surfaced through :mod:`quanttrade.core.security`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigError

ENV_PREFIX = "QT_"
DEFAULT_CONFIG_PATH = Path("config/config.yaml")


def _load_dotenv(path: Path) -> None:
    """Minimal ``.env`` loader (avoids a hard dependency on python-dotenv)."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _coerce(value: str) -> Any:
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"none", "null"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _env_overrides() -> dict:
    """Translate ``QT_RISK__MAX_DAILY_LOSS=500`` -> {'risk': {'max_daily_loss': 500}}."""
    result: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX):].lower().split("__")
        cursor = result
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path[-1]] = _coerce(value)
    return result


DEFAULTS: dict[str, Any] = {
    "app": {"name": "QuantTrade", "env": "development", "timezone": "America/New_York"},
    "trading": {"mode": "paper", "base_currency": "USD"},
    "data": {"provider": "synthetic", "cache_dir": ".cache", "cache_ttl_seconds": 3600},
    "broker": {"name": "paper", "starting_cash": 100_000.0, "commission_per_share": 0.005,
               "slippage_bps": 1.0},
    "risk": {
        "max_daily_loss_pct": 0.03,
        "max_drawdown_pct": 0.20,
        "max_position_pct": 0.10,
        "max_gross_exposure_pct": 1.5,
        "max_sector_pct": 0.30,
        "max_correlation": 0.85,
        "default_risk_per_trade_pct": 0.01,
        "kelly_fraction": 0.5,
    },
    "database": {"url": "sqlite:///quanttrade.db", "echo": False},
    "api": {"host": "0.0.0.0", "port": 8000, "cors_origins": ["*"]},
    "logging": {"level": "INFO", "dir": "logs", "json": False},
}


@dataclass
class Config:
    """Immutable-ish configuration container with dotted-path access."""

    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None, *, dotenv: str | Path = ".env") -> "Config":
        _load_dotenv(Path(dotenv))
        merged = dict(DEFAULTS)

        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if cfg_path.exists():
            try:
                file_cfg = yaml.safe_load(cfg_path.read_text()) or {}
            except yaml.YAMLError as exc:  # pragma: no cover - defensive
                raise ConfigError(f"Invalid YAML in {cfg_path}: {exc}") from exc
            merged = _deep_merge(merged, file_cfg)

        merged = _deep_merge(merged, _env_overrides())
        return cls(merged)

    def get(self, dotted: str, default: Any = None) -> Any:
        return _walk(self.data, dotted, default)

    def require(self, dotted: str) -> Any:
        sentinel = object()
        value = _walk(self.data, dotted, sentinel)
        if value is sentinel:
            raise ConfigError(f"Required config key missing: {dotted}")
        return value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]


def _walk(data: dict, dotted: str, default: Any) -> Any:
    cursor: Any = data
    for part in dotted.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return default
        cursor = cursor[part]
    return cursor


_active: Config | None = None


def get_config(reload: bool = False) -> Config:
    """Return the process-wide config singleton."""
    global _active
    if _active is None or reload:
        _active = Config.load()
    return _active
