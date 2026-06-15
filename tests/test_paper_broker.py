"""Tests for the paper-trading broker."""
import pytest

from quanttrade.brokers import PaperBroker
from quanttrade.core.enums import OrderSide, OrderStatus, OrderType
from quanttrade.models import Order


@pytest.fixture
def broker():
    b = PaperBroker(starting_cash=100_000.0, commission_per_share=0.0, slippage_bps=0.0)
    b.connect()
    b.update_price("AAPL", 100.0)
    return b


def test_market_buy_fills(broker):
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    broker.submit_order(order)
    assert order.status == OrderStatus.FILLED
    assert order.avg_fill_price == 100.0
    assert broker.cash == 100_000.0 - 1000.0


def test_position_tracking(broker):
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10))
    pos = broker.get_position("AAPL")
    assert pos.quantity == 10
    assert pos.avg_price == 100.0


def test_round_trip_pnl(broker):
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10))
    broker.update_price("AAPL", 110.0)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.SELL, quantity=10))
    # Bought 10@100 (=-1000), sold 10@110 (=+1100) -> +100 net.
    assert broker.cash == pytest.approx(100_100.0)
    assert broker.get_position("AAPL") is None  # closed


def test_insufficient_funds_rejected(broker):
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10_000)  # 1,000,000 > cash
    broker.submit_order(order)
    assert order.status == OrderStatus.REJECTED


def test_limit_order_rests_then_fills(broker):
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10,
                  order_type=OrderType.LIMIT, limit_price=95.0)
    broker.submit_order(order)
    assert order.status == OrderStatus.SUBMITTED  # price 100 > 95, no fill
    broker.update_price("AAPL", 94.0)             # crosses limit
    assert order.status == OrderStatus.FILLED


def test_cancel_open_order(broker):
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10,
                  order_type=OrderType.LIMIT, limit_price=90.0)
    broker.submit_order(order)
    assert broker.cancel_order(order.id) is True
    assert order.status == OrderStatus.CANCELLED


def test_account_equity(broker):
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10))
    broker.update_price("AAPL", 120.0)
    acct = broker.get_account()
    # cash 99,000 + position 10*120 = 100,200
    assert acct.equity == pytest.approx(100_200.0)
