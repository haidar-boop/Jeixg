"""Momentum / oscillator indicators.

RSI, Stochastic, ROC, Momentum, Williams %R and CCI. All vectorized over
pandas objects and aligned to the input index. No future data is used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "rsi",
    "stochastic",
    "roc",
    "momentum",
    "williams_r",
    "cci",
]


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 14
        Lookback period.

    Returns
    -------
    pd.Series
        RSI values in the range [0, 100]. Warmup values are NaN.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi_series = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is zero, RSI is 100 by definition.
    rsi_series = rsi_series.where(avg_loss != 0.0, 100.0)
    # Preserve warmup NaNs.
    rsi_series = rsi_series.where(avg_gain.notna())
    return rsi_series.rename("rsi")


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """Stochastic oscillator (%K and %D).

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    k_period : int, default 14
        Lookback for the %K calculation.
    d_period : int, default 3
        Smoothing window (SMA) for %D.

    Returns
    -------
    pd.DataFrame
        Columns ``k`` and ``d``, both in [0, 100].
    """
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    rng = (highest_high - lowest_low).replace(0.0, np.nan)
    k = 100.0 * (close - lowest_low) / rng
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return pd.DataFrame({"k": k, "d": d})


def roc(close: pd.Series, period: int = 12) -> pd.Series:
    """Rate of Change (percentage).

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 12
        Number of periods to look back.

    Returns
    -------
    pd.Series
        ``100 * (close / close.shift(period) - 1)``.
    """
    shifted = close.shift(period)
    return (100.0 * (close / shifted - 1.0)).rename("roc")


def momentum(close: pd.Series, period: int = 10) -> pd.Series:
    """Momentum: difference between price now and ``period`` bars ago.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 10
        Lookback period.

    Returns
    -------
    pd.Series
        ``close - close.shift(period)``.
    """
    return (close - close.shift(period)).rename("momentum")


def williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Williams %R.

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    period : int, default 14
        Lookback period.

    Returns
    -------
    pd.Series
        Values in [-100, 0].
    """
    highest_high = high.rolling(window=period, min_periods=period).max()
    lowest_low = low.rolling(window=period, min_periods=period).min()
    rng = (highest_high - lowest_low).replace(0.0, np.nan)
    wr = -100.0 * (highest_high - close) / rng
    return wr.rename("williams_r")


def cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Commodity Channel Index.

    Uses the typical price and the mean absolute deviation (Lambert's
    constant 0.015).

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    period : int, default 20
        Lookback period.

    Returns
    -------
    pd.Series
        CCI values. Warmup values are NaN.
    """
    typical_price = (high + low + close) / 3.0
    sma_tp = typical_price.rolling(window=period, min_periods=period).mean()
    mean_dev = typical_price.rolling(window=period, min_periods=period).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )
    cci_series = (typical_price - sma_tp) / (0.015 * mean_dev)
    return cci_series.rename("cci")
