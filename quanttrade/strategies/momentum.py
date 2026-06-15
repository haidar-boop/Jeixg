"""Momentum and breakout strategies."""
from __future__ import annotations

import pandas as pd

from ..core.enums import SignalType
from ..indicators import atr, rsi
from ..models import Signal
from .base import Strategy, StrategyContext, register_strategy


@register_strategy("momentum")
class Momentum(Strategy):
    """Rate-of-change momentum with an RSI confirmation filter."""

    def on_init(self) -> None:
        self.lookback = int(self.params.get("lookback", 20))
        self.threshold = float(self.params.get("threshold", 0.05))
        self.rsi_floor = float(self.params.get("rsi_floor", 50))
        self.warmup = self.lookback + 15

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        close = data["close"]
        roc = close.iloc[-1] / close.iloc[-self.lookback] - 1.0
        r = float(rsi(close).iloc[-1])
        price = float(close.iloc[-1])
        symbol = data.attrs.get("symbol", "")
        if roc > self.threshold and r > self.rsi_floor and not context.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, strength=min(roc / self.threshold, 1.0),
                           price=price, strategy=self.name)]
        if context.has_position(symbol) and roc < 0:
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []


@register_strategy("breakout")
class Breakout(Strategy):
    """Donchian-channel breakout: buy N-day high breaks, trail an ATR stop."""

    def on_init(self) -> None:
        self.channel = int(self.params.get("channel", 20))
        self.atr_mult = float(self.params.get("atr_mult", 2.5))
        self.warmup = self.channel + 2

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        # Prior channel excludes the current bar (no lookahead).
        prior_high = data["high"].iloc[-self.channel - 1:-1].max()
        prior_low = data["low"].iloc[-self.channel - 1:-1].min()
        price = float(data["close"].iloc[-1])
        a = float(atr(data["high"], data["low"], data["close"]).iloc[-1])
        symbol = data.attrs.get("symbol", "")
        if price > prior_high and not context.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, strength=1.0, price=price,
                           stop_loss=price - self.atr_mult * a, strategy=self.name)]
        if price < prior_low and context.has_position(symbol):
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []
