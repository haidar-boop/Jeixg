"""Core enumerations shared across the QuantTrade platform.

Centralising these enums keeps the domain vocabulary consistent across the
data, broker, strategy, risk and persistence layers.
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-backed enum so values serialise cleanly to JSON / databases."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class AssetClass(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    OPTION = "option"
    FUTURE = "future"
    FOREX = "forex"
    CRYPTO = "crypto"
    PENNY_STOCK = "penny_stock"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"  # good-til-cancelled
    IOC = "ioc"  # immediate-or-cancel
    FOK = "fok"  # fill-or-kill


class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class TradingMode(StrEnum):
    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"
    FORWARD_TEST = "forward_test"


class SignalType(StrEnum):
    """Discrete trading intent emitted by a strategy."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"
    SCALE_IN = "scale_in"
    SCALE_OUT = "scale_out"


class BarInterval(StrEnum):
    SEC_1 = "1s"
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"


class EventType(StrEnum):
    MARKET_DATA = "market_data"
    SIGNAL = "signal"
    ORDER = "order"
    FILL = "fill"
    RISK_BREACH = "risk_breach"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
