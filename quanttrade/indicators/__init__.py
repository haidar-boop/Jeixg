"""Technical-analysis indicator engine for quanttrade.

This package provides from-scratch (no TA-Lib), vectorized pandas/numpy
implementations of common technical indicators. All indicators operate on
pandas Series / DataFrames indexed by timestamp and return results aligned to
the input index.

Public API is re-exported here so users can simply do::

    from quanttrade.indicators import rsi, macd, atr, bollinger_bands
"""

from __future__ import annotations

from .fibonacci import fibonacci_extensions, fibonacci_retracements
from .ichimoku import ichimoku
from .momentum import cci, momentum, roc, rsi, stochastic, williams_r
from .structure import (
    detect_breakout,
    detect_trend,
    support_resistance,
    swing_highs_lows,
)
from .trend import adx, ema, macd, sma, supertrend, wma
from .volatility import (
    atr,
    bollinger_bands,
    historical_volatility,
    keltner_channels,
)
from .volume import (
    accumulation_distribution,
    mfi,
    obv,
    volume_profile,
    vwap,
)

__all__ = [
    # trend
    "sma",
    "ema",
    "wma",
    "macd",
    "adx",
    "supertrend",
    # momentum
    "rsi",
    "stochastic",
    "roc",
    "momentum",
    "williams_r",
    "cci",
    # volatility
    "atr",
    "bollinger_bands",
    "keltner_channels",
    "historical_volatility",
    # volume
    "obv",
    "vwap",
    "volume_profile",
    "mfi",
    "accumulation_distribution",
    # ichimoku
    "ichimoku",
    # fibonacci
    "fibonacci_retracements",
    "fibonacci_extensions",
    # structure
    "swing_highs_lows",
    "support_resistance",
    "detect_trend",
    "detect_breakout",
]
