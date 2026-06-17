"""Market-hours awareness.

Prefers the broker's own market clock (e.g. Alpaca's, which knows holidays). Falls
back to US Eastern regular hours (Mon-Fri, 9:30-16:00 ET) when no clock is
available. If it genuinely can't tell, it assumes open so the bot isn't silently
idle.
"""
from __future__ import annotations

from datetime import datetime, time

from ..core.logging_config import get_logger

logger = get_logger(__name__)

_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def is_market_open(broker=None) -> bool:
    # 1. Broker clock (authoritative; accounts for holidays).
    if broker is not None and hasattr(broker, "get_clock"):
        try:
            clock = broker.get_clock()
            if isinstance(clock, dict) and "is_open" in clock:
                return bool(clock["is_open"])
        except Exception:  # noqa: BLE001
            logger.debug("broker clock unavailable; using time-based fallback")

    # 2. Time-based fallback (US Eastern regular session, no holiday calendar).
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:  # pragma: no cover - tz data missing
        return True
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    return _OPEN <= now.time() <= _CLOSE
