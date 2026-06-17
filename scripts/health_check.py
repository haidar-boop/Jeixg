#!/usr/bin/env python3
"""Health check: text you if the bot has stopped updating its heartbeat.

The bot writes a heartbeat every cycle. This script reads it and, if it's stale
(the bot likely crashed or was stopped), sends one SMS alert. Run it as a
PythonAnywhere **Scheduled task** (e.g. hourly):

    /home/<USER>/Jeixg/.venv/bin/python /home/<USER>/Jeixg/scripts/health_check.py

It only alerts during US market hours (when the bot should be active) and won't
spam: it writes a marker so it alerts at most once per stale episode.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quanttrade.core.config import get_config  # noqa: E402
from quanttrade.execution.market_hours import is_market_open  # noqa: E402
from quanttrade.notifications import create_notifier  # noqa: E402

HEARTBEAT = ROOT / "heartbeat.txt"
ALERTED = ROOT / ".health_alerted"
STALE_SECONDS = 15 * 60  # alert if no heartbeat for 15 minutes


def main() -> None:
    get_config()  # loads .env so Twilio creds are available
    if not is_market_open():
        return  # bot is meant to be idle outside market hours

    now = time.time()
    last = float(HEARTBEAT.read_text().strip()) if HEARTBEAT.exists() else 0.0
    stale = (now - last) > STALE_SECONDS

    if stale and not ALERTED.exists():
        mins = int((now - last) / 60) if last else 999
        create_notifier().send(
            "QuantTrade ALERT",
            f"The bot hasn't checked in for ~{mins} min during market hours. "
            f"It may have stopped — check your PythonAnywhere Always-on task.")
        ALERTED.write_text(str(now))
    elif not stale and ALERTED.exists():
        ALERTED.unlink()  # recovered -> reset so future outages alert again


if __name__ == "__main__":
    main()
