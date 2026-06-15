"""Tests for the persistence layer."""
from datetime import datetime, timezone

import pytest

from quanttrade.core.enums import OrderSide, OrderStatus, PositionSide
from quanttrade.models import Order, Trade
from quanttrade.persistence import (
    Database,
    OrderRepository,
    TradeRepository,
)
from quanttrade.persistence.repositories import AuditRepository, BarRepository


@pytest.fixture
def db():
    database = Database("sqlite:///:memory:")
    database.create_all()
    return database


def test_order_roundtrip(db):
    repo = OrderRepository(db)
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    repo.save(order)
    loaded = repo.get(order.id)
    assert loaded.symbol == "AAPL"
    assert loaded.side == OrderSide.BUY


def test_order_status_update(db):
    repo = OrderRepository(db)
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    repo.save(order)
    repo.update_status(order.id, OrderStatus.FILLED)
    assert repo.get(order.id).status == OrderStatus.FILLED


def test_trade_journal(db):
    repo = TradeRepository(db)
    now = datetime.now(timezone.utc)
    repo.save(Trade(symbol="AAPL", side=PositionSide.LONG, quantity=10,
                    entry_price=100, exit_price=110, entry_time=now,
                    exit_time=now, pnl=100))
    assert len(repo.list()) == 1
    assert repo.aggregate_pnl() == 100.0


def test_bar_cache(db, ohlcv):
    repo = BarRepository(db)
    n = repo.upsert_bars("AAPL", "1d", ohlcv.head(50))
    assert n == 50
    # Idempotent upsert.
    assert repo.upsert_bars("AAPL", "1d", ohlcv.head(50)) == 0
    fetched = repo.get_bars("AAPL", "1d")
    assert len(fetched) == 50


def test_audit_log(db):
    repo = AuditRepository(db)
    repo.log(actor="tester", action="login", detail={"ip": "127.0.0.1"})
    recent = repo.recent()
    assert recent[0]["action"] == "login"
