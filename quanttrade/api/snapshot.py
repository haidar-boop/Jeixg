"""Watchlist snapshot shared from the bot to the dashboard.

The dashboard web app on PythonAnywhere can't reliably fetch market data, but the
bot (an always-on task) can. So the bot computes the watchlist each cycle and
writes it here; the dashboard simply reads this file. This decouples the web app
from market-data fetching entirely -> fast and reliable.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..core.enums import SignalType
from ..core.logging_config import get_logger
from ..indicators import rsi
from ..indicators.structure import detect_trend
from ..strategies import StrategyRegistry
from ..strategies.base import StrategyContext

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path() -> Path:
    return Path(os.getenv("QT_WATCHLIST_PATH") or (PROJECT_ROOT / "watchlist.json"))


def build_watchlist_rows(bars: dict, positions: dict, strategy_name: str) -> list[dict]:
    """Compute per-symbol signal + indicators from pre-fetched bars."""
    # The ensemble is portfolio-level -> use its allocator for the watchlist.
    if strategy_name == "ensemble":
        try:
            from ..strategies.ensemble import EnsembleAllocator
            rows = EnsembleAllocator().detail(bars)
            for r in rows:
                r["held"] = r["symbol"] in positions
                r["position_qty"] = 0
            return rows
        except Exception:  # noqa: BLE001
            logger.exception("ensemble watchlist failed")
            return []
    try:
        strategy = StrategyRegistry.create(strategy_name)
    except Exception:  # noqa: BLE001
        from ..strategies import RSIReversion
        strategy = RSIReversion()
    warmup = getattr(strategy, "warmup", 50)
    rows: list[dict] = []
    for symbol, df in bars.items():
        try:
            if df is None:
                continue
            df = df.dropna()  # drop blank rows so we never emit NaN prices
            if len(df) < warmup:
                continue
            df = df.copy()
            df.attrs["symbol"] = symbol
            last = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2]) if len(df) > 1 else last
            ctx = StrategyContext(positions=positions)
            signals = strategy.generate_signals(df, ctx)
            signal = signals[0].type.value if signals else SignalType.HOLD.value
            held = symbol in positions and abs(getattr(positions[symbol], "quantity", 0)) > 1e-9
            rows.append({
                "symbol": symbol,
                "last_price": round(last, 2),
                "change_pct": round(last / prev - 1, 4) if prev else 0.0,
                "signal": signal,
                "rsi": round(float(rsi(df["close"]).iloc[-1]), 1),
                "trend": str(detect_trend(df["close"]).iloc[-1]),
                "held": held,
                "position_qty": round(positions[symbol].quantity, 4) if held else 0,
            })
        except Exception:  # noqa: BLE001
            logger.exception("watchlist row failed for %s", symbol)
    return rows


def write_watchlist(rows: list[dict]) -> None:
    try:
        path = _path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"updated": time.time(), "rows": rows}))
        tmp.replace(path)
    except OSError:  # pragma: no cover
        logger.exception("could not write watchlist snapshot")


def read_watchlist(max_age: float = 3600.0) -> list[dict] | None:
    """Return the bot's last watchlist if it's fresh enough, else None."""
    path = _path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if time.time() - float(data.get("updated", 0)) > max_age:
        return None
    return data.get("rows")
