"""Momentum and breakout strategies."""
from __future__ import annotations

import pandas as pd

from ..core.enums import SignalType
from ..indicators import atr, rsi, sma
from ..models import Signal
from .base import Strategy, StrategyContext, register_strategy


@register_strategy("trend_momentum")
class TrendMomentum(Strategy):
    """Time-series (trend-following) momentum -- the best-evidenced systematic
    strategy (159 years / 40 countries of out-of-sample support).

    Hold an asset while it's in a confirmed uptrend; exit when the trend breaks.

    * Entry: price above its long-term moving average **and** positive momentum
      over the lookback window.
    * Exit: price falls below the trend MA, or momentum turns negative.
    * An ATR-based stop is attached for risk control, echoing the volatility
      scaling shown to roughly halve momentum drawdowns.
    """

    def on_init(self) -> None:
        self.trend_ma = int(self.params.get("trend_ma", 200))
        self.lookback = int(self.params.get("lookback", 120))   # ~6 months
        self.atr_mult = float(self.params.get("atr_mult", 3.0))
        self.warmup = max(self.trend_ma, self.lookback) + 5

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        close = data["close"]
        price = float(close.iloc[-1])
        trend_ma = float(sma(close, self.trend_ma).iloc[-1])
        momentum = price / float(close.iloc[-self.lookback]) - 1.0
        symbol = data.attrs.get("symbol", "")

        in_uptrend = price > trend_ma and momentum > 0
        if in_uptrend and not context.has_position(symbol):
            a = float(atr(data["high"], data["low"], close).iloc[-1])
            return [Signal(symbol, SignalType.BUY,
                           strength=min(max(momentum, 0.0) / 0.20, 1.0), price=price,
                           stop_loss=price - self.atr_mult * a, strategy=self.name,
                           metadata={"reason": f"uptrend +{momentum:.0%} over {self.lookback}d, "
                                               f"above {self.trend_ma}d avg"})]
        if context.has_position(symbol) and (price < trend_ma or momentum < 0):
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []


@register_strategy("trend_pullback")
class TrendPullback(Strategy):
    """A synthesis strategy: 'buy strong uptrends on a pullback, ride the trend.'

    Rationale -- plain trend-following has a real edge but tends to *enter when a
    stock is already extended*, then gets stopped out on normal noise. This keeps
    the evidenced trend/momentum edge but improves the entry and holds winners:

    * **Regime filter** (the edge): only go long when price is above its long
      moving average AND momentum over the lookback is positive -- i.e. a genuine
      uptrend (time-series momentum).
    * **Entry timing** (the tweak): don't buy when extended; wait for a *pullback*
      within that uptrend (RSI dips below ``buy_rsi``) to get a better price.
    * **Exit** (let winners run): close only when the trend breaks (price falls
      below the long MA). An ATR stop bounds the downside.

    Not magic -- it's a reasoned combination of components that each have
    evidence. Validate before trusting it.
    """

    def on_init(self) -> None:
        self.trend_ma = int(self.params.get("trend_ma", 200))
        self.lookback = int(self.params.get("lookback", 120))
        self.buy_rsi = float(self.params.get("buy_rsi", 45))
        self.atr_mult = float(self.params.get("atr_mult", 3.0))
        self.warmup = max(self.trend_ma, self.lookback) + 5

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        close = data["close"]
        price = float(close.iloc[-1])
        trend_ma = float(sma(close, self.trend_ma).iloc[-1])
        momentum = price / float(close.iloc[-self.lookback]) - 1.0
        r = float(rsi(close).iloc[-1])
        symbol = data.attrs.get("symbol", "")

        in_uptrend = price > trend_ma and momentum > 0
        if in_uptrend and r < self.buy_rsi and not context.has_position(symbol):
            a = float(atr(data["high"], data["low"], close).iloc[-1])
            return [Signal(symbol, SignalType.BUY, strength=(self.buy_rsi - r) / self.buy_rsi,
                           price=price, stop_loss=price - self.atr_mult * a, strategy=self.name,
                           metadata={"reason": f"uptrend pullback (RSI {r:.0f}, +{momentum:.0%})"})]
        if context.has_position(symbol) and price < trend_ma:
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []


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
