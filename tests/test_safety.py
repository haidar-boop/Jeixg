"""Tests for the safety controls: kill-switch, flatten, protective stops, hours."""
import datetime

import pytest

from quanttrade.brokers import PaperBroker
from quanttrade.core.enums import OrderSide, OrderType
from quanttrade.data import create_data_provider
from quanttrade.execution.approval_engine import ApprovalTradingEngine
from quanttrade.execution.market_hours import is_market_open
from quanttrade.models import Order
from quanttrade.notifications import Notifier
from quanttrade.notifications.approvals import ApprovalStore
from quanttrade.notifications.control import ControlStore
from quanttrade.risk import FixedRiskSizer, RiskLimits, RiskManager
from quanttrade.strategies import RSIReversion


class _Quiet(Notifier):
    name = "q"
    def _send(self, s, m): ...


def test_control_store_halt(tmp_path):
    c = ControlStore(tmp_path / "control.json")
    assert not c.is_halted()
    c.set_halt(True)
    assert c.is_halted()
    c.set_halt(False)
    assert not c.is_halted()


def test_control_store_flatten_is_one_shot(tmp_path):
    c = ControlStore(tmp_path / "control.json")
    assert c.pop_flatten() is False
    c.request_flatten()
    assert c.pop_flatten() is True
    assert c.pop_flatten() is False  # cleared after popping


def test_market_hours_fallback_weekend(monkeypatch):
    import quanttrade.execution.market_hours as mh

    class _Sat(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 13, 12, 0, tzinfo=tz)  # Saturday

    monkeypatch.setattr(mh, "datetime", _Sat)
    assert is_market_open(broker=None) is False


def _engine():
    broker = PaperBroker(starting_cash=100_000, commission_per_share=0, slippage_bps=0)
    broker.connect()
    df = create_data_provider("synthetic").get_historical_bars(
        "AAPL", datetime.datetime(2023, 1, 1), datetime.datetime(2024, 1, 1))
    broker.update_price("AAPL", float(df["close"].iloc[-1]))
    eng = ApprovalTradingEngine(
        RSIReversion(), broker, create_data_provider("synthetic"), ["AAPL"],
        auto_symbols=["AAPL"], notifier=_Quiet(),
        store=ApprovalStore("/tmp/_t_approvals.json"),
        sizer=FixedRiskSizer(0.0075, fractional=True),
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.9)))
    eng.start()
    return eng, broker


def test_protective_stop_placed():
    eng, broker = _engine()
    broker.submit_order(Order("AAPL", OrderSide.BUY, 10, OrderType.MARKET))
    eng.protect_positions(0.08)
    stops = [o for o in broker.get_open_orders() if o.order_type == OrderType.STOP]
    assert len(stops) == 1
    pos = broker.get_positions()[0]
    assert stops[0].stop_price == pytest.approx(round(pos.avg_price * 0.92, 2))


def test_flatten_clears_everything():
    eng, broker = _engine()
    broker.submit_order(Order("AAPL", OrderSide.BUY, 10, OrderType.MARKET))
    eng.protect_positions(0.08)
    sold = eng.flatten_all()
    assert sold == 1
    assert broker.get_positions() == []
    assert broker.get_open_orders() == []


def test_capital_cap_limits_total_deployment(tmp_path):
    """Regression: max_capital caps TOTAL deployed money, not just per position."""
    import datetime as _dt

    from quanttrade.core.enums import SignalType
    from quanttrade.models import Signal
    from quanttrade.notifications.approvals import ApprovalStore
    from quanttrade.strategies.base import Strategy

    class AlwaysBuy(Strategy):
        warmup = 1
        def generate_signals(self, data, ctx):
            sym = data.attrs.get("symbol", "")
            if ctx.has_position(sym):
                return []
            price = float(data["close"].iloc[-1])
            return [Signal(sym, SignalType.BUY, strength=0.9, price=price,
                           stop_loss=price * 0.95, metadata={"reason": "x"})]

    broker = PaperBroker(starting_cash=100_000, commission_per_share=0, slippage_bps=0)
    broker.connect()
    prov = create_data_provider("synthetic")
    syms = ["AAPL", "MSFT", "NVDA", "SPY", "JPM", "XOM", "KO", "V"]
    for s in syms:
        df = prov.get_historical_bars(s, _dt.datetime(2023, 1, 1), _dt.datetime(2024, 1, 1))
        broker.update_price(s, float(df["close"].iloc[-1]))
    eng = ApprovalTradingEngine(
        AlwaysBuy(), broker, prov, syms, auto_symbols=syms, notifier=_Quiet(),
        store=ApprovalStore(tmp_path / "a.json"),
        sizer=FixedRiskSizer(0.0075, fractional=True),
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.9, max_gross_exposure_pct=10.0)),
        max_capital=1000,
    )
    eng.start()
    for _ in range(8):
        eng._auto_buy_trusted(broker.get_account().equity)
    deployed = sum(abs(p.market_value) for p in broker.get_positions())
    assert deployed <= 1050  # stays within the $1000 cap (small rounding headroom)


def test_new_day_clears_halt():
    """Bug 2: a daily-loss halt must clear when a new trading day starts
    (the live loop now calls start_day automatically), without a restart."""
    rm = RiskManager(RiskLimits(max_daily_loss_pct=0.03))
    rm.start_day(1000)
    rm.update_equity(950)        # -5% loss -> trips the daily-loss halt
    assert rm.halted is True
    rm.start_day(950)            # new trading day rolls over
    assert rm.halted is False    # halt cleared automatically -- no restart needed


def test_sell_all_pauses_and_does_not_rebuy(tmp_path, monkeypatch):
    """SELL ALL must flatten AND pause, so the bot doesn't instantly re-buy."""
    import datetime as _dt

    import run_bot
    from quanttrade.core.enums import SignalType
    from quanttrade.models import Signal
    from quanttrade.notifications import Notifier
    from quanttrade.notifications.approvals import ApprovalStore
    from quanttrade.notifications.control import ControlStore
    from quanttrade.strategies.base import Strategy

    monkeypatch.setattr(run_bot, "is_market_open", lambda b=None: True)
    monkeypatch.setattr(run_bot, "HEARTBEAT_PATH", tmp_path / "hb.txt")
    monkeypatch.setenv("QT_WATCHLIST_PATH", str(tmp_path / "wl.json"))

    class _Q(Notifier):
        name = "q"
        def _send(self, s, m): ...

    class AlwaysBuy(Strategy):
        warmup = 1
        def generate_signals(self, data, ctx):
            sym = data.attrs.get("symbol", "")
            if ctx.has_position(sym):
                return []
            price = float(data["close"].iloc[-1])
            return [Signal(sym, SignalType.BUY, strength=0.9, price=price,
                           stop_loss=price * 0.95, metadata={"reason": "x"})]

    broker = PaperBroker(starting_cash=100_000, commission_per_share=0, slippage_bps=0)
    broker.connect()
    prov = create_data_provider("synthetic")
    syms = ["AAPL", "MSFT", "NVDA"]
    for s in syms:
        df = prov.get_historical_bars(s, _dt.datetime(2023, 1, 1), _dt.datetime(2024, 1, 1))
        broker.update_price(s, float(df["close"].iloc[-1]))
    eng = ApprovalTradingEngine(
        AlwaysBuy(), broker, prov, syms, auto_symbols=syms, notifier=_Q(),
        store=ApprovalStore(tmp_path / "a.json"),
        sizer=FixedRiskSizer(0.0075, fractional=True),
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.9, max_gross_exposure_pct=10.0)),
        max_capital=1000)
    ctrl = ControlStore(tmp_path / "control.json")
    state: dict = {}
    eng.start()
    run_bot.run_cycle(eng, ctrl, state, 0.08)
    assert len(broker.get_positions()) > 0      # bought

    ctrl.request_flatten()
    run_bot.run_cycle(eng, ctrl, state, 0.08)
    run_bot.run_cycle(eng, ctrl, state, 0.08)   # extra cycle: must NOT re-buy
    assert broker.get_positions() == []
    assert ctrl.is_halted() is True


def test_always_open_trades_when_market_closed(tmp_path, monkeypatch):
    """The crypto bot's --always-open must trade even when the stock market is shut."""
    import datetime as _dt

    import run_bot
    from quanttrade.core.enums import SignalType
    from quanttrade.models import Signal
    from quanttrade.notifications import Notifier
    from quanttrade.notifications.approvals import ApprovalStore
    from quanttrade.notifications.control import ControlStore
    from quanttrade.strategies.base import Strategy

    # Stock market is CLOSED -> the normal gate would skip trading.
    monkeypatch.setattr(run_bot, "is_market_open", lambda b=None: False)
    monkeypatch.setattr(run_bot, "HEARTBEAT_PATH", tmp_path / "hb.txt")
    monkeypatch.setenv("QT_WATCHLIST_PATH", str(tmp_path / "wl.json"))

    class _Q(Notifier):
        name = "q"
        def _send(self, s, m): ...

    class AlwaysBuy(Strategy):
        warmup = 1
        def generate_signals(self, data, ctx):
            sym = data.attrs.get("symbol", "")
            if ctx.has_position(sym):
                return []
            price = float(data["close"].iloc[-1])
            return [Signal(sym, SignalType.BUY, strength=0.9, price=price,
                           stop_loss=price * 0.95, metadata={"reason": "x"})]

    broker = PaperBroker(starting_cash=100_000, commission_per_share=0, slippage_bps=0)
    broker.connect()
    prov = create_data_provider("synthetic")
    syms = ["BTC-USD", "ETH-USD"]
    for s in syms:
        df = prov.get_historical_bars(s, _dt.datetime(2023, 1, 1), _dt.datetime(2024, 1, 1))
        broker.update_price(s, float(df["close"].iloc[-1]))
    eng = ApprovalTradingEngine(
        AlwaysBuy(), broker, prov, syms, auto_symbols=syms, notifier=_Q(),
        store=ApprovalStore(tmp_path / "a.json"),
        sizer=FixedRiskSizer(0.0075, fractional=True),
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.9, max_gross_exposure_pct=10.0)),
        max_capital=1000)
    ctrl = ControlStore(tmp_path / "control.json")
    eng.start()

    # Without always_open: market closed -> no trades.
    run_bot.run_cycle(eng, ctrl, {}, 0.08, always_open=False)
    assert broker.get_positions() == []
    # With always_open: trades 24/7 despite the closed stock market.
    run_bot.run_cycle(eng, ctrl, {}, 0.08, always_open=True)
    assert len(broker.get_positions()) > 0


def test_heartbeat_path_env_override(tmp_path, monkeypatch):
    """A second bot instance must be able to write its OWN heartbeat (no collision)."""
    import importlib

    monkeypatch.setenv("QT_HEARTBEAT_PATH", str(tmp_path / "heartbeat_crypto.txt"))
    import run_bot
    importlib.reload(run_bot)
    try:
        assert run_bot.HEARTBEAT_PATH == tmp_path / "heartbeat_crypto.txt"
        run_bot._write_heartbeat()
        assert (tmp_path / "heartbeat_crypto.txt").exists()
    finally:
        monkeypatch.delenv("QT_HEARTBEAT_PATH", raising=False)
        importlib.reload(run_bot)   # restore default for other tests
