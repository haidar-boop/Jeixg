"""yfinance-backed market data provider.

Wraps the optional ``yfinance`` package to pull free historical equity/ETF/crypto
data from Yahoo Finance. The dependency is imported lazily so the platform runs
without it (falling back to the synthetic provider).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ...core.enums import BarInterval
from ...core.exceptions import DataProviderError
from ...core.logging_config import get_logger
from ..base import MarketDataProvider

logger = get_logger(__name__)

_INTERVAL_MAP = {
    BarInterval.MIN_1: "1m",
    BarInterval.MIN_5: "5m",
    BarInterval.MIN_15: "15m",
    BarInterval.MIN_30: "30m",
    BarInterval.HOUR_1: "60m",
    BarInterval.DAY_1: "1d",
    BarInterval.WEEK_1: "1wk",
}


class YFinanceDataProvider(MarketDataProvider):
    """Historical data via Yahoo Finance (requires ``pip install yfinance``)."""

    name = "yfinance"

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional dep
            raise DataProviderError(
                "yfinance not installed. Run `pip install yfinance` or use the "
                "synthetic provider."
            ) from exc

    def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: BarInterval = BarInterval.DAY_1,
    ) -> pd.DataFrame:
        import yfinance as yf

        yf_interval = _INTERVAL_MAP.get(interval, "1d")
        try:
            raw = yf.download(
                symbol, start=start, end=end, interval=yf_interval,
                progress=False, auto_adjust=True,
            )
        except Exception as exc:  # noqa: BLE001 - normalise provider failures
            raise DataProviderError(f"yfinance download failed for {symbol}: {exc}") from exc

        if raw is None or raw.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # yfinance may return a MultiIndex column frame for single symbols.
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns=str.lower)
        df = raw[["open", "high", "low", "close", "volume"]].copy()
        df.index.name = "timestamp"
        return df
