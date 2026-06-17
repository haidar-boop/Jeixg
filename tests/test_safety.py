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
