"""Mean-reversion strategies."""
from __future__ import annotations

import pandas as pd

from ..core.enums import SignalType
from ..indicators import bollinger_bands, rsi
from ..models import Signal
from .base import Strategy, StrategyContext, register_strategy


@register_strategy("bollinger_reversion")
class BollingerReversion(Strategy):
    """Buy lower-band touches, exit at the mean (middle band)."""

    def on_init(self) -> None:
        self.period = int(self.params.get("period", 20))
        self.num_std = float(self.params.get("num_std", 2.0))
        self.warmup = self.period + 2

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        bb = bollinger_bands(data["close"], self.period, self.num_std)
        price = float(data["close"].iloc[-1])
        lower = float(bb["lower"].iloc[-1])
        mid = float(bb["middle"].iloc[-1])
        symbol = data.attrs.get("symbol", "")

        if price <= lower and not context.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, strength=1.0, price=price,
                           stop_loss=price * 0.95, take_profit=mid, strategy=self.name)]
        if context.has_position(symbol) and price >= mid:
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []


@register_strategy("rsi_reversion")
class RSIReversion(Strategy):
    """Buy oversold (RSI < lower), exit when RSI recovers above ``exit_level``."""

    def on_init(self) -> None:
        self.period = int(self.params.get("period", 14))
        self.lower = float(self.params.get("lower", 30))
        self.exit_level = float(self.params.get("exit_level", 55))
        self.warmup = self.period + 2

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        r = float(rsi(data["close"], self.period).iloc[-1])
        price = float(data["close"].iloc[-1])
        symbol = data.attrs.get("symbol", "")
        if r < self.lower and not context.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, strength=(self.lower - r) / self.lower,
                           price=price, stop_loss=price * 0.95, strategy=self.name,
                           metadata={"reason": f"RSI {r:.0f}, oversold"})]
        if context.has_position(symbol) and r > self.exit_level:
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []
