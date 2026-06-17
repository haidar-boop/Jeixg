#!/usr/bin/env python3
"""QuantTrade bot runner -- the single entry point that *runs the bot*.

Wires up a strategy + broker + data feed + risk manager into a
:class:`~quanttrade.execution.engine.TradingEngine` and drives the decision loop.

Two run modes (so it works locally AND on schedulers like PythonAnywhere):

  * continuous loop (default)::

        python run_bot.py --strategy ma_crossover --symbols AAPL,MSFT --interval 60

  * single pass then exit (for cron / PythonAnywhere "Scheduled tasks")::

        python run_bot.py --once --strategy ma_crossover --symbols AAPL,MSFT

Everything is configurable via flags or env/`config.yaml`. Defaults to the
PAPER broker + synthetic data so it runs safely with no credentials.
"""
from __future__ import annotations

import argparse
import signal
import time

from quanttrade.brokers import create_broker
from quanttrade.core.config import get_config
from quanttrade.core.logging_config import get_logger, setup_logging
from quanttrade.data import create_data_provider
from quanttrade.execution import TradingEngine
from quanttrade.execution.approval_engine import ApprovalTradingEngine
from quanttrade.execution.market_hours import is_market_open
from quanttrade.notifications.control import ControlStore
from quanttrade.risk import FixedRiskSizer, RiskLimits, RiskManager
from quanttrade.strategies import StrategyRegistry  # noqa: F401
import quanttrade.strategies  # noqa: F401  (registers built-in strategies)

from datetime import datetime
from pathlib import Path

logger = get_logger("run_bot")
_RUNNING = True

# Heartbeat file: updated every cycle so an external health check can tell the
# bot is alive (see scripts/health_check.py).
HEARTBEAT_PATH = Path(__file__).resolve().parent / "heartbeat.txt"

# The trusted core: traded automatically, no approval needed.
DEFAULT_AUTO = "AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ"

# A broader pool to hunt across; anything here NOT in the trusted core needs
# your YES/NO approval before buying.
DEFAULT_UNIVERSE = (
    DEFAULT_AUTO + ",AVGO,COST,HD,BAC,DIS,PYPL,INTC,CRM,PFE,KO,PEP,CSCO,ORCL,"
    "ADBE,QCOM,UBER,SHOP,COIN,PLTR,SOFI,BA,GE,F,T,MU"
)


def _handle_signal(signum, _frame):
    global _RUNNING
    logger.info("Received signal %s -- shutting down after current cycle", signum)
    _RUNNING = False


def build_engine(args):
    cfg = get_config()
    broker = create_broker(
        args.broker,
        **({"starting_cash": args.cash} if args.broker in {"paper", "sim"} else {}),
    )
    broker.connect()
    data = create_data_provider(args.provider)
    strategy = StrategyRegistry.create(args.strategy)
    risk = RiskManager(RiskLimits.from_config(cfg))
    # Use fractional shares when the broker supports them (lets a small budget
    # buy expensive stocks instead of rounding down to zero).
    sizer = FixedRiskSizer(risk_pct=cfg.get("risk.default_risk_per_trade_pct", 0.01),
                           fractional=getattr(broker, "supports_fractional", False))
    max_capital = args.max_capital or float(cfg.get("broker.max_capital", 0) or 0)

    if args.require_approval:
        universe = [s.strip().upper() for s in (args.universe or args.symbols).split(",") if s.strip()]
        auto = [s.strip().upper() for s in args.auto_symbols.split(",") if s.strip()]
        engine = ApprovalTradingEngine(
            strategy=strategy, broker=broker, data_provider=data, universe=universe,
            auto_symbols=auto, sizer=sizer, risk_manager=risk, max_capital=max_capital,
        )
    else:
        engine = TradingEngine(
            strategy=strategy, broker=broker, data_provider=data,
            symbols=[s.strip().upper() for s in args.symbols.split(",")],
            sizer=sizer, risk_manager=risk, max_capital=max_capital,
        )
    if max_capital:
        logger.info("Capital cap: bot will deploy at most $%.2f", max_capital)
    engine.start()
    return engine


def _write_heartbeat() -> None:
    try:
        HEARTBEAT_PATH.write_text(str(time.time()))
    except OSError:  # pragma: no cover
        logger.debug("could not write heartbeat")


def _daily_summary(engine, state: dict) -> None:
    """Text an end-of-day summary when the market closes."""
    broker = engine.broker
    try:
        acct = broker.get_account()
        raw = broker.get_account_raw() if hasattr(broker, "get_account_raw") else {}
        last_eq = float(raw.get("last_equity") or acct.equity)
        day_pnl = acct.equity - last_eq
        n_pos = len([p for p in broker.get_positions() if abs(p.quantity) > 1e-9])
    except Exception:  # noqa: BLE001
        logger.exception("daily summary failed")
        return
    sign = "+" if day_pnl >= 0 else "-"
    pct = (day_pnl / last_eq) if last_eq else 0.0
    engine.notifier.send(
        "QuantTrade daily summary",
        f"Market closed. Equity ${acct.equity:,.2f} | day P&L {sign}${abs(day_pnl):,.2f} "
        f"({pct:+.2%}) | {n_pos} positions held.")


def run_cycle(engine, control: ControlStore, state: dict, stop_pct: float) -> None:
    _write_heartbeat()
    broker = engine.broker
    open_now = is_market_open(broker)

    # Kill-switch: "SELL ALL" texted -> flatten everything.
    if control.pop_flatten() and hasattr(engine, "flatten_all"):
        n = engine.flatten_all()
        engine.notifier.send("QuantTrade",
                             f"Flattened: sold {n} positions and cancelled open orders.")

    # Daily summary fires exactly when the session flips open -> closed.
    if state.get("market_was_open") and not open_now:
        _daily_summary(engine, state)
    state["market_was_open"] = open_now

    if not open_now:
        logger.info("Market closed - idle (no trading).")
        return
    if control.is_halted():
        logger.info("Trading halted (you texted STOP) - skipping buys.")
        return

    engine.run_once()
    if hasattr(engine, "protect_positions"):
        engine.protect_positions(stop_pct)

    account = broker.get_account()
    logger.info("Cycle done | equity=%.2f positions=%d",
                account.equity, len([p for p in broker.get_positions()
                                     if abs(p.quantity) > 1e-9]))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the QuantTrade bot")
    parser.add_argument("--strategy", default="ma_crossover")
    parser.add_argument("--symbols", default="AAPL,MSFT,GOOG")
    parser.add_argument("--broker", default="paper",
                        help="paper | alpaca | tradier | ... (live brokers need creds)")
    parser.add_argument("--provider", default="synthetic",
                        help="synthetic | yfinance")
    parser.add_argument("--cash", type=float, default=100_000.0,
                        help="starting cash for the paper broker")
    parser.add_argument("--interval", type=int, default=60,
                        help="seconds between cycles in loop mode")
    parser.add_argument("--require-approval", action="store_true",
                        help="auto-trade the core list; text for YES/NO on the rest")
    parser.add_argument("--auto-symbols", default=DEFAULT_AUTO,
                        help="trusted tickers traded automatically (no approval)")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE,
                        help="full pool to scan; non-core tickers need approval")
    parser.add_argument("--max-capital", type=float, default=0.0,
                        help="cap total money the bot will deploy (0 = no cap)")
    parser.add_argument("--stop-loss-pct", type=float, default=-1.0,
                        help="protective stop distance, e.g. 0.08 (default: config)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                      help="run a single cycle then exit (for cron/schedulers)")
    mode.add_argument("--loop", action="store_true",
                      help="run continuously (the default; explicit for clarity)")
    args = parser.parse_args(argv)

    cfg = get_config()
    setup_logging(level=cfg.get("logging.level", "INFO"))
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    stop_pct = (args.stop_loss_pct if args.stop_loss_pct >= 0
                else float(cfg.get("risk.protective_stop_pct", 0.08) or 0.0))
    control = ControlStore()
    state: dict = {}

    try:
        engine = build_engine(args)
    except Exception:  # noqa: BLE001 - startup failure -> alert and exit
        logger.exception("Bot failed to start")
        _alert("QuantTrade ALERT: the bot failed to start. Check the logs.")
        raise

    logger.info("Bot started: %s | broker=%s data=%s | stop=%.0f%%",
                args.strategy, args.broker, args.provider, stop_pct * 100)

    if args.once:
        run_cycle(engine, control, state, stop_pct)
        engine.stop()
        return

    errors = 0
    while _RUNNING:
        try:
            run_cycle(engine, control, state, stop_pct)
            errors = 0
        except Exception:  # noqa: BLE001 - survive transient errors, alert if persistent
            errors += 1
            logger.exception("Cycle failed (%d in a row); continuing", errors)
            if errors == 3:
                _alert("QuantTrade ALERT: the bot hit repeated errors but is still "
                       "retrying. Check the PythonAnywhere task log.")
        for _ in range(args.interval):
            if not _RUNNING:
                break
            time.sleep(1)
    engine.stop()
    logger.info("Bot stopped cleanly")


def _alert(message: str) -> None:
    """Best-effort SMS alert that never raises."""
    try:
        from quanttrade.notifications import create_notifier
        create_notifier().send("QuantTrade", message)
    except Exception:  # noqa: BLE001
        logger.exception("could not send alert")


if __name__ == "__main__":
    main()
