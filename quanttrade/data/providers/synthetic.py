"""Synthetic market-data provider.

Generates deterministic geometric-Brownian-motion price series so the platform
can be developed, demoed and tested with zero external dependencies or network
access. Used as the default provider and throughout the test-suite.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from ...core.enums import BarInterval
from ...models import Quote
from ..base import MarketDataProvider

_INTERVAL_FREQ = {
    BarInterval.MIN_1: "1min",
    BarInterval.MIN_5: "5min",
    BarInterval.MIN_15: "15min",
    BarInterval.MIN_30: "30min",
    BarInterval.HOUR_1: "1h",
    BarInterval.HOUR_4: "4h",
    BarInterval.DAY_1: "1D",
    BarInterval.WEEK_1: "1W",
}


class SyntheticDataProvider(MarketDataProvider):
    """Deterministic GBM OHLCV generator (seeded per symbol)."""

    name = "synthetic"

    def __init__(self, mu: float = 0.08, sigma: float = 0.2,
                 start_price: float = 100.0, seed: int = 42) -> None:
        self.mu = mu
        self.sigma = sigma
        self.start_price = start_price
        self.seed = seed

    def _symbol_seed(self, symbol: str) -> int:
        return (self.seed + sum(ord(c) for c in symbol)) % (2**32)

    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: BarInterval = BarInterval.DAY_1,
    ) -> pd.DataFrame:
        freq = _INTERVAL_FREQ.get(interval, "1D")
        idx = pd.date_range(start=start, end=end, freq=freq)
        if len(idx) == 0:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        rng = np.random.default_rng(self._symbol_seed(symbol))
        n = len(idx)
        # Per-step drift/vol scaled to the bar frequency (assume 252 trading days).
        dt = 1.0 / 252.0 if interval == BarInterval.DAY_1 else 1.0 / (252.0 * 390.0)
        shocks = rng.normal(
            (self.mu - 0.5 * self.sigma**2) * dt,
            self.sigma * np.sqrt(dt),
            size=n,
        )
        close = self.start_price * np.exp(np.cumsum(shocks))

        # Build OHLC consistent with the close path.
        intrabar = self.sigma * np.sqrt(dt)
        open_ = np.empty(n)
        open_[0] = self.start_price
        open_[1:] = close[:-1]
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, intrabar, n)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, intrabar, n)))
        volume = rng.lognormal(mean=13.0, sigma=0.5, size=n).round()

        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )
        df.index.name = "timestamp"
        return df

    def get_latest_quote(self, symbol: str) -> Quote:
        end = datetime.utcnow()
        start = end - pd.Timedelta(days=5)
        bars = self.get_historical_bars(symbol, start, end)
        last = float(bars["close"].iloc[-1]) if len(bars) else self.start_price
        return Quote(symbol=symbol, bid=last * 0.9995, ask=last * 1.0005,
                     bid_size=100, ask_size=100)
