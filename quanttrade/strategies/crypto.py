"""Crypto strategies.

A starter momentum/breakout strategy aimed at "find cheap coins that are starting
to run up, ride them, and cut losers fast." It is deliberately simple and heavily
commented so you can edit the rules yourself -- every knob is in ``on_init`` via
``self.params`` so you can tune it without touching the logic.

How it decides (per coin, on daily bars):
  BUY  when the coin is in an uptrend (price above its long moving average) AND it
       just broke out to a new N-day high with real upward momentum.
  SELL when momentum rolls over (price falls back below the short moving average)
       -- plus a hard protective stop set at entry.

This works on any price series, so it runs on crypto symbols (BTC-USD, DOGE-USD,
...) exactly like the stock strategies. It is NOT financial advice and NOT proven
to make money -- backtest it before trusting it.
"""
from __future__ import annotations

import pandas as pd

from ..core.enums import SignalType
from ..indicators import atr, rsi, sma
from ..models import Signal
from .base import Strategy, StrategyContext, register_strategy


@register_strategy("crypto_momentum")
class CryptoMomentum(Strategy):
    """Trend-filtered breakout momentum for crypto. Tune via params."""

    def on_init(self) -> None:
        # --- knobs you can tune -------------------------------------------
        self.trend_ma = int(self.params.get("trend_ma", 50))      # long trend filter
        self.exit_ma = int(self.params.get("exit_ma", 10))        # short exit trigger
        self.breakout = int(self.params.get("breakout", 20))      # N-day high to break
        self.mom_lookback = int(self.params.get("mom_lookback", 14))
        self.min_momentum = float(self.params.get("min_momentum", 0.05))  # +5% over lookback
        self.rsi_ceiling = float(self.params.get("rsi_ceiling", 80))      # don't chase blow-offs
        self.atr_mult = float(self.params.get("atr_mult", 3.0))   # protective stop distance
        self.warmup = max(self.trend_ma, self.breakout) + 5

    def generate_signals(self, data: pd.DataFrame, context: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        close = data["close"]
        price = float(close.iloc[-1])
        symbol = data.attrs.get("symbol", "")

        trend = float(sma(close, self.trend_ma).iloc[-1])
        short = float(sma(close, self.exit_ma).iloc[-1])
        # Prior channel high excludes today's bar so there's no look-ahead.
        prior_high = float(data["high"].iloc[-self.breakout - 1:-1].max())
        momentum = price / float(close.iloc[-self.mom_lookback]) - 1.0
        r = float(rsi(close).iloc[-1])
        a = float(atr(data["high"], data["low"], data["close"]).iloc[-1])

        # --- BUY: uptrend + fresh breakout + real momentum, but not overheated ---
        if (not context.has_position(symbol)
                and price > trend                       # in an uptrend
                and price > prior_high                  # breaking out to new highs
                and momentum > self.min_momentum        # actually running up
                and r < self.rsi_ceiling):              # not a vertical blow-off
            strength = min(momentum / self.min_momentum, 1.0)
            return [Signal(symbol, SignalType.BUY, strength=strength, price=price,
                           stop_loss=price - self.atr_mult * a, strategy=self.name)]

        # --- SELL: momentum rolled over (lost the short MA) ---
        if context.has_position(symbol) and price < short:
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []
