"""Tests for domain models, especially Position P&L accounting."""
from quanttrade.core.enums import OrderSide, PositionSide
from quanttrade.models import Position


def test_open_long_sets_avg_price():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.BUY, 10, 100.0)
    assert pos.quantity == 10
    assert pos.avg_price == 100.0
    assert pos.side == PositionSide.LONG


def test_add_to_long_weighted_average():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.BUY, 10, 100.0)
    pos.apply_fill(OrderSide.BUY, 10, 120.0)
    assert pos.quantity == 20
    assert pos.avg_price == 110.0


def test_close_long_realizes_pnl():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.BUY, 10, 100.0)
    realized = pos.apply_fill(OrderSide.SELL, 10, 110.0)
    assert realized == 100.0
    assert pos.quantity == 0
    assert pos.realized_pnl == 100.0


def test_partial_close():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.BUY, 10, 100.0)
    realized = pos.apply_fill(OrderSide.SELL, 4, 110.0)
    assert realized == 40.0
    assert pos.quantity == 6
    assert pos.avg_price == 100.0


def test_flip_long_to_short():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.BUY, 10, 100.0)
    realized = pos.apply_fill(OrderSide.SELL, 15, 110.0)
    # Closed 10 @ +10 = +100 realized; remaining 5 short opened at 110.
    assert realized == 100.0
    assert pos.quantity == -5
    assert pos.avg_price == 110.0
    assert pos.side == PositionSide.SHORT


def test_short_pnl():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.SELL, 10, 100.0)  # open short
    realized = pos.apply_fill(OrderSide.BUY, 10, 90.0)  # cover lower -> profit
    assert realized == 100.0


def test_unrealized_pnl():
    pos = Position("AAPL")
    pos.apply_fill(OrderSide.BUY, 10, 100.0)
    pos.last_price = 105.0
    assert pos.unrealized_pnl == 50.0
    assert pos.market_value == 1050.0
