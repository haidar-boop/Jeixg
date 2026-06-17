#!/usr/bin/env python3
"""QuantTrade self-check ("doctor").

Runs through every major part of the platform and prints a clear PASS / WARN /
FAIL report, so you can confirm everything works after an update.

Run it:
    .venv/bin/python scripts/check.py
    # add --text to also send a real test SMS to your phone:
    .venv/bin/python scripts/check.py --text
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "✅", "⚠️ ", "❌"
results: list[tuple[str, str]] = []


def check(label: str, fn) -> None:
    try:
        status, detail = fn()
    except Exception as exc:  # noqa: BLE001
        status, detail = FAIL, f"{type(exc).__name__}: {exc}"
    results.append((status, label))
    print(f"  {status}  {label}: {detail}")


def main() -> None:
    send_text = "--text" in sys.argv

    # Load .env from the project root so credentials are visible.
    from quanttrade.core.config import _load_dotenv, get_config
    _load_dotenv(ROOT / ".env")
    get_config(reload=True)

    print("\nQuantTrade self-check\n" + "=" * 40)

    def c_import():
        import quanttrade
        return OK, f"package v{quanttrade.__version__} imported"
    check("Platform install", c_import)

    def c_config():
        cfg = get_config()
        return OK, f"strategy={cfg.get('trading.strategy')}, mode={cfg.get('trading.mode')}"
    check("Configuration", c_config)

    def c_env():
        return (OK, ".env found") if (ROOT / ".env").exists() else (WARN, "no .env file")
    check("Secrets file", c_env)

    def c_twilio():
        keys = ["QT_TWILIO_ACCOUNT_SID", "QT_TWILIO_AUTH_TOKEN", "QT_TWILIO_FROM", "QT_TWILIO_TO"]
        missing = [k for k in keys if not os.getenv(k)]
        return (OK, "configured") if not missing else (WARN, f"missing {', '.join(missing)}")
    check("SMS (Twilio) setup", c_twilio)

    def c_alpaca():
        if not os.getenv("QT_ALPACA_API_KEY"):
            return WARN, "no Alpaca keys in .env (using paper simulator)"
        from quanttrade.brokers import create_broker
        b = create_broker("alpaca")
        b.connect()
        acct = b.get_account()
        return OK, f"connected, equity ${acct.equity:,.2f}"
    check("Broker connection (Alpaca)", c_alpaca)

    def c_data():
        from quanttrade.data import create_data_provider
        prov = create_data_provider("yfinance")
        end = datetime.now(timezone.utc)
        df = prov.get_historical_bars("AAPL", end - timedelta(days=10), end)
        if df is None or len(df) == 0:
            return WARN, "no data returned (network/yfinance issue)"
        return OK, f"{len(df)} AAPL bars, last close ${float(df['close'].iloc[-1]):,.2f}"
    check("Market data feed", c_data)

    def c_strategy():
        import quanttrade.strategies  # noqa: F401
        from quanttrade.strategies import StrategyRegistry
        name = get_config().get("trading.strategy", "rsi_reversion")
        StrategyRegistry.create(name)
        return OK, f"'{name}' loaded ({len(StrategyRegistry.available())} available)"
    check("Strategy", c_strategy)

    def c_backtest():
        from quanttrade.backtest import BacktestEngine
        from quanttrade.data import create_data_provider
        from quanttrade.risk import RiskLimits, RiskManager
        from quanttrade.strategies import MovingAverageCrossover
        prov = create_data_provider("synthetic")
        data = {"AAPL": prov.get_historical_bars("AAPL", datetime(2021, 1, 1), datetime(2023, 1, 1))}
        res = BacktestEngine(MovingAverageCrossover(),
                             risk_manager=RiskManager(RiskLimits(max_position_pct=0.5,
                                                                 max_daily_loss_pct=0.5,
                                                                 max_drawdown_pct=0.9))).run(data)
        return OK, f"ran, {res.performance.trades.num_trades} trades"
    check("Backtest engine", c_backtest)

    def c_stores():
        from quanttrade.notifications.approvals import ApprovalStore
        from quanttrade.notifications.control import ControlStore
        ControlStore().status()
        ApprovalStore().list_requests()
        return OK, "approval + control stores readable"
    check("Approval / control state", c_stores)

    def c_heartbeat():
        hb = ROOT / "heartbeat.txt"
        if not hb.exists():
            return WARN, "no heartbeat yet (bot hasn't run in this folder)"
        age = time.time() - float(hb.read_text().strip())
        if age < 600:
            return OK, f"bot active ({int(age)}s ago)"
        return WARN, f"last beat {int(age // 60)} min ago (bot stopped, or market closed)"
    check("Bot heartbeat", c_heartbeat)

    if send_text:
        def c_sms():
            from quanttrade.notifications import create_notifier
            ok = create_notifier().send("QuantTrade self-check", "Test text - everything is wired up.")
            return (OK, "test SMS sent") if ok else (WARN, "send returned false")
        check("Send test SMS", c_sms)

    print("=" * 40)
    fails = sum(1 for s, _ in results if s == FAIL)
    warns = sum(1 for s, _ in results if s == WARN)
    passed = sum(1 for s, _ in results if s == OK)
    print(f"Result: {passed} passed, {warns} warnings, {fails} failed.")
    if fails:
        print("Something needs attention — see the ❌ lines above.")
        sys.exit(1)
    if warns:
        print("All core systems OK. Warnings are usually fine (e.g. market closed).")
    else:
        print("Everything looks good. 🎉")


if __name__ == "__main__":
    main()
