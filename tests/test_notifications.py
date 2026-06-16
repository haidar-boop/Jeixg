"""Tests for trade notifications."""
from quanttrade.brokers import PaperBroker
from quanttrade.core.enums import OrderSide, OrderType
from quanttrade.data import create_data_provider
from quanttrade.execution import TradingEngine
from quanttrade.models import Order
from quanttrade.notifications import LogNotifier, Notifier, create_notifier


class RecordingNotifier(Notifier):
    name = "recording"

    def __init__(self):
        self.messages = []

    def _send(self, subject, message):
        self.messages.append((subject, message))


def test_create_notifier_defaults_to_log(monkeypatch):
    for key in ("QT_TWILIO_ACCOUNT_SID", "QT_TWILIO_AUTH_TOKEN",
                "QT_TWILIO_FROM", "QT_TWILIO_TO"):
        monkeypatch.delenv(key, raising=False)
    assert isinstance(create_notifier(), LogNotifier)


def test_notifier_never_raises():
    class Boom(Notifier):
        name = "boom"
        def _send(self, subject, message):
            raise RuntimeError("network down")

    # send() must swallow the error and report failure rather than propagate.
    assert Boom().send("x", "y") is False


def _engine_with(notifier):
    broker = PaperBroker(starting_cash=100_000, commission_per_share=0.0, slippage_bps=0.0)
    broker.connect()
    broker.update_price("AAPL", 100.0)
    from quanttrade.strategies import MovingAverageCrossover
    eng = TradingEngine(MovingAverageCrossover(), broker,
                        create_data_provider("synthetic"), ["AAPL"], notifier=notifier)
    eng.start()
    return eng, broker


def test_entry_notification():
    cap = RecordingNotifier()
    eng, broker = _engine_with(cap)
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, order_type=OrderType.MARKET)
    broker.submit_order(order)
    eng._record_and_notify(order)
    bodies = [m for _, m in cap.messages]
    assert any("BUY 10 AAPL" in b for b in bodies)


def test_exit_notification_reports_profit():
    cap = RecordingNotifier()
    eng, broker = _engine_with(cap)
    buy = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, order_type=OrderType.MARKET)
    broker.submit_order(buy)
    eng._record_and_notify(buy)
    broker.update_price("AAPL", 110.0)
    sell = Order(symbol="AAPL", side=OrderSide.SELL, quantity=10, order_type=OrderType.MARKET)
    broker.submit_order(sell)
    eng._record_and_notify(sell)
    subjects = [s for s, _ in cap.messages]
    bodies = [m for _, m in cap.messages]
    assert any("WON" in s for s in subjects)
    assert any("+$100.00" in b for b in bodies)
