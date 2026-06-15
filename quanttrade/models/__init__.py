"""Domain models for QuantTrade.

These dataclasses are the lingua franca between layers (data, broker, strategy,
risk, persistence). They are deliberately framework-agnostic -- no SQLAlchemy or
pydantic coupling -- so they can be used in tight backtest loops cheaply.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..core.enums import (
    AssetClass,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SignalType,
    TimeInForce,
)


def _uid() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Instrument:
    """A tradable instrument."""

    symbol: str
    asset_class: AssetClass = AssetClass.STOCK
    exchange: str = "SMART"
    currency: str = "USD"
    multiplier: float = 1.0  # contract multiplier (options=100, futures vary)
    sector: str = "unknown"

    def __str__(self) -> str:
        return f"{self.symbol}:{self.asset_class}"


@dataclass
class Bar:
    """OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0


@dataclass
class Quote:
    """Top-of-book quote."""

    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    timestamp: datetime = field(default_factory=_now)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class Signal:
    """Strategy output -- an intent, not yet an order."""

    symbol: str
    type: SignalType
    strength: float = 1.0  # 0..1 conviction
    price: float | None = None  # reference price at signal time
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy: str = ""
    timestamp: datetime = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    """An order request and its lifecycle state."""

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    trail_amount: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    id: str = field(default_factory=_uid)
    broker_order_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    strategy: str = ""
    account_id: str = ""
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in {
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        }

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def remaining(self) -> float:
        return max(self.quantity - self.filled_quantity, 0.0)


@dataclass
class Fill:
    """An execution against an order."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float = 0.0
    timestamp: datetime = field(default_factory=_now)
    id: str = field(default_factory=_uid)


@dataclass
class Position:
    """A held position with running P&L accounting."""

    symbol: str
    quantity: float = 0.0  # signed: negative = short
    avg_price: float = 0.0
    last_price: float = 0.0
    realized_pnl: float = 0.0
    asset_class: AssetClass = AssetClass.STOCK
    sector: str = "unknown"
    opened_at: datetime = field(default_factory=_now)

    @property
    def side(self) -> PositionSide:
        if self.quantity > 0:
            return PositionSide.LONG
        if self.quantity < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.avg_price) * self.quantity

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    def apply_fill(self, side: OrderSide, quantity: float, price: float,
                   commission: float = 0.0) -> float:
        """Update the position with a fill. Returns realized P&L from this fill.

        Handles opening, adding, reducing, closing and flipping in one place so
        broker, paper and backtest engines share identical accounting.
        """
        signed = quantity if side == OrderSide.BUY else -quantity
        realized = 0.0
        if self.quantity == 0 or (self.quantity > 0) == (signed > 0):
            # Opening or increasing in the same direction -> weighted avg price.
            new_qty = self.quantity + signed
            if new_qty != 0:
                self.avg_price = (
                    self.avg_price * self.quantity + price * signed
                ) / new_qty
            self.quantity = new_qty
        else:
            # Reducing / closing / flipping.
            closing = min(abs(signed), abs(self.quantity))
            direction = 1 if self.quantity > 0 else -1
            realized = (price - self.avg_price) * closing * direction
            self.quantity += signed
            if (self.quantity > 0) != (self.quantity - signed > 0) and self.quantity != 0:
                # Flipped through zero -> remainder opens a new position at price.
                self.avg_price = price
            elif self.quantity == 0:
                self.avg_price = 0.0
        self.realized_pnl += realized - commission
        self.last_price = price
        return realized - commission


@dataclass
class Trade:
    """A completed round-trip (entry + exit) for the journal/analytics."""

    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    commission: float = 0.0
    strategy: str = ""
    id: str = field(default_factory=_uid)
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def return_pct(self) -> float:
        cost = self.entry_price * abs(self.quantity)
        return self.pnl / cost if cost else 0.0

    @property
    def holding_period(self):
        return self.exit_time - self.entry_time


@dataclass
class AccountSnapshot:
    """Point-in-time account state."""

    cash: float
    equity: float
    buying_power: float
    positions_value: float = 0.0
    margin_used: float = 0.0
    timestamp: datetime = field(default_factory=_now)
    account_id: str = "default"
