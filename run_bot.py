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
from quanttrade.risk import FixedRiskSizer, RiskLimits, RiskManager
from quanttrade.strategies import StrategyRegistry  # noqa: F401
import quanttrade.strategies  # noqa: F401  (registers built-in strategies)

logger = get_logger("run_bot")
_RUNNING = True

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


def run_cycle(engine) -> None:
    results = engine.run_once()
    account = engine.broker.get_account()
    positions = len(engine.broker.get_positions())
    halted = " | HALTED: " + engine.risk.halt_reason if engine.risk.halted else ""
    if isinstance(results, dict) and "outstanding" in results:
        waiting = " | awaiting your YES/NO reply" if results["outstanding"] else ""
        logger.info("Cycle done | equity=%.2f positions=%d%s%s",
                    account.equity, positions, waiting, halted)
    else:
        submitted = sum(len(orders) for orders in results.values())
        logger.info("Cycle done | equity=%.2f cash=%.2f orders=%d positions=%d%s",
                    account.equity, account.cash, submitted, positions, halted)


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                      help="run a single cycle then exit (for cron/schedulers)")
    mode.add_argument("--loop", action="store_true",
                      help="run continuously (the default; explicit for clarity)")
    args = parser.parse_args(argv)

    setup_logging(level=get_config().get("logging.level", "INFO"))
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    engine = build_engine(args)
    logger.info("Bot started: %s on %s via %s broker (%s data)",
                args.strategy, args.symbols, args.broker, args.provider)

    if args.once:
        run_cycle(engine)
        engine.stop()
        return

    while _RUNNING:
        try:
            run_cycle(engine)
        except Exception:  # noqa: BLE001 - keep the bot alive across transient errors
            logger.exception("Cycle failed; continuing")
        # Sleep in short slices so signals are handled promptly.
        for _ in range(args.interval):
            if not _RUNNING:
                break
            time.sleep(1)
    engine.stop()
    logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    main()
