"""Volatility indicators: ATR, Bollinger Bands, Keltner Channels and HV."""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "atr",
    "bollinger_bands",
    "keltner_channels",
    "historical_volatility",
]


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Compute the True Range series."""
    prev_close = close.shift(1)
    return pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range using Wilder's smoothing.

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    period : int, default 14
        Smoothing period.

    Returns
    -------
    pd.Series
        ATR series. Warmup values are NaN.
    """
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean().rename("atr")


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 20
        Lookback window for the middle band (SMA) and standard deviation.
    num_std : float, default 2.0
        Number of standard deviations for the bands.

    Returns
    -------
    pd.DataFrame
        Columns ``upper``, ``middle``, ``lower``, ``bandwidth`` and
        ``percent_b``.
    """
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    bandwidth = (upper - lower) / middle.replace(0.0, np.nan)
    rng = (upper - lower).replace(0.0, np.nan)
    percent_b = (close - lower) / rng
    return pd.DataFrame(
        {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth,
            "percent_b": percent_b,
        }
    )


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    atr_mult: float = 2.0,
) -> pd.DataFrame:
    """Keltner Channels (EMA midline, ATR-based bands).

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    period : int, default 20
        Period for the EMA midline and the ATR.
    atr_mult : float, default 2.0
        ATR multiplier for the band offset.

    Returns
    -------
    pd.DataFrame
        Columns ``upper``, ``middle`` and ``lower``.
    """
    middle = close.ewm(span=period, adjust=False, min_periods=period).mean()
    channel_atr = atr(high, low, close, period=period)
    upper = middle + atr_mult * channel_atr
    lower = middle - atr_mult * channel_atr
    return pd.DataFrame({"upper": upper, "middle": middle, "lower": lower})


def historical_volatility(
    close: pd.Series,
    period: int = 20,
    annualize: int = 252,
) -> pd.Series:
    """Historical (realized) volatility from log returns.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 20
        Rolling window over which to compute the standard deviation of log
        returns.
    annualize : int, default 252
        Number of periods per year used to annualize the volatility. Pass 1
        to leave it un-annualized.

    Returns
    -------
    pd.Series
        Annualized volatility (a fraction, e.g. 0.20 == 20%).
    """
    log_returns = np.log(close / close.shift(1))
    rolling_std = log_returns.rolling(window=period, min_periods=period).std(ddof=1)
    return (rolling_std * np.sqrt(annualize)).rename("historical_volatility")
