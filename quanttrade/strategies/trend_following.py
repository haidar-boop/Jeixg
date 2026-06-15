"""Trend-following strategies."""
from __future__ import annotations

import pandas as pd

from ..core.enums import SignalType
from ..indicators import atr, ema, sma
from ..models import Signal
from .base import Strategy, StrategyContext, register_strategy


@register_strategy("ma_crossover")
class MovingAverageCrossover(Strategy):
    """Classic dual moving-average crossover.

    Long when the fast MA crosses above the slow MA; exit/short on the reverse.
    A stop is placed at ``atr_mult`` ATRs below entry.
    """

    def on_init(self) -> None:
        self.fast = int(self.params.get("fast", 20))
        self.slow = int(self.params.get("slow", 50))
        self.atr_mult = float(self.params.get("atr_mult", 2.0))
        self.use_ema = bool(self.params.get("use_ema", False))
        self.warmup = self.slow + 2

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        ma = ema if self.use_ema else sma
        fast = ma(data["close"], self.fast)
        slow = ma(data["close"], self.slow)
        a = atr(data["high"], data["low"], data["close"]).iloc[-1]
        price = float(data["close"].iloc[-1])
        symbol = data.attrs.get("symbol", "")

        cross_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        cross_down = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]

        if cross_up and not context.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, strength=1.0, price=price,
                           stop_loss=price - self.atr_mult * a, strategy=self.name)]
        if cross_down and context.has_position(symbol):
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []


@register_strategy("trend_strength")
class TrendStrength(Strategy):
    """Trade in the direction of an EMA stack (fast>mid>slow = strong uptrend)."""

    def on_init(self) -> None:
        self.fast = int(self.params.get("fast", 10))
        self.mid = int(self.params.get("mid", 30))
        self.slow = int(self.params.get("slow", 60))
        self.warmup = self.slow + 2

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        close = data["close"]
        f, m, s = ema(close, self.fast).iloc[-1], ema(close, self.mid).iloc[-1], ema(close, self.slow).iloc[-1]
        price = float(close.iloc[-1])
        symbol = data.attrs.get("symbol", "")
        if f > m > s and not context.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, strength=1.0, price=price, strategy=self.name)]
        if f < m and context.has_position(symbol):
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []
