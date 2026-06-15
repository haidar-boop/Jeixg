"""QuantTrade -- a modular algorithmic trading platform.

Public API re-exports the most commonly used building blocks so that user code
and example strategies can ``from quanttrade import Strategy, Signal, ...``.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .core.config import Config, get_config
from .core.enums import (
    AssetClass,
    OrderSide,
    OrderStatus,
    OrderType,
    SignalType,
    TradingMode,
)
from .core.logging_config import get_logger, setup_logging
from .models import (
    AccountSnapshot,
    Bar,
    Fill,
    Instrument,
    Order,
    Position,
    Quote,
    Signal,
    Trade,
)

__all__ = [
    "__version__",
    "Config",
    "get_config",
    "setup_logging",
    "get_logger",
    "AssetClass",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "SignalType",
    "TradingMode",
    "Instrument",
    "Bar",
    "Quote",
    "Signal",
    "Order",
    "Fill",
    "Position",
    "Trade",
    "AccountSnapshot",
]
