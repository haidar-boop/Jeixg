"""Passive strategies."""
from __future__ import annotations

import pandas as pd

from ..core.enums import SignalType
from ..models import Signal
from .base import Strategy, StrategyContext, register_strategy


@register_strategy("buy_and_hold")
class BuyAndHold(Strategy):
    """Buy each symbol once and hold it indefinitely -- never sells.

    The simplest, and historically one of the hardest-to-beat, approaches: take a
    position in each name and ride it. There are no exit signals, so position
    sizing should be done with a fixed-fraction sizer (equal weight), not a
    stop-based one. Pair it with stops disabled for a true buy-and-hold.
    """

    warmup = 1

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        symbol = data.attrs.get("symbol", "")
        if context.has_position(symbol):
            return []
        price = float(data["close"].iloc[-1])
        return [Signal(symbol, SignalType.BUY, strength=1.0, price=price,
                       strategy=self.name, metadata={"reason": "buy & hold"})]
