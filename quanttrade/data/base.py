"""Market-data provider interface.

A provider supplies historical bars (for backtesting / feature engineering) and,
optionally, a streaming quote feed (for live/paper). Concrete providers
(yfinance, Alpaca, synthetic) implement this contract so the rest of the
platform never depends on a specific vendor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, Iterable

import pandas as pd

from ..core.enums import BarInterval
from ..models import Quote


class MarketDataProvider(ABC):
    """Abstract base for all market-data sources."""

    name: str = "base"

    @abstractmethod
    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: BarInterval = BarInterval.DAY_1,
    ) -> pd.DataFrame:
        """Return a DataFrame indexed by timestamp with OHLCV columns.

        Columns (lowercase): ``open, high, low, close, volume``.
        """

    def get_multiple(
        self,
        symbols: Iterable[str],
        start: datetime,
        end: datetime,
        interval: BarInterval = BarInterval.DAY_1,
    ) -> dict[str, pd.DataFrame]:
        """Convenience batch fetch. Providers may override for efficiency."""
        return {s: self.get_historical_bars(s, start, end, interval) for s in symbols}

    def get_latest_quote(self, symbol: str) -> Quote:  # pragma: no cover - optional
        raise NotImplementedError(f"{self.name} does not support quotes")

    async def stream_quotes(
        self, symbols: Iterable[str]
    ) -> AsyncIterator[Quote]:  # pragma: no cover - optional
        raise NotImplementedError(f"{self.name} does not support streaming")
        yield  # pragma: no cover - makes this an async generator
