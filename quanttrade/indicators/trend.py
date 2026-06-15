"""Trend indicators: moving averages, MACD, ADX and Supertrend.

All functions are vectorized over pandas objects and return results aligned to
the input index. No lookahead bias is introduced: only rolling / exponential
windows over past data are used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "sma",
    "ema",
    "wma",
    "macd",
    "adx",
    "supertrend",
]


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average.

    Parameters
    ----------
    series : pd.Series
        Input series (typically close prices).
    period : int
        Lookback window length.

    Returns
    -------
    pd.Series
        Rolling arithmetic mean. The first ``period - 1`` values are NaN.
    """
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average (recursive, ``adjust=False``).

    Parameters
    ----------
    series : pd.Series
        Input series.
    period : int
        Span of the EMA; the smoothing factor is ``2 / (period + 1)``.

    Returns
    -------
    pd.Series
        The exponential moving average aligned to ``series``.
    """
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average with linearly increasing weights.

    The most recent observation receives weight ``period`` and the oldest
    observation in the window receives weight ``1``.

    Parameters
    ----------
    series : pd.Series
        Input series.
    period : int
        Lookback window length.

    Returns
    -------
    pd.Series
        Linearly weighted moving average. First ``period - 1`` values are NaN.
    """
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()

    def _wma(window: np.ndarray) -> float:
        return float(np.dot(window, weights) / weight_sum)

    return series.rolling(window=period, min_periods=period).apply(_wma, raw=True)


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Moving Average Convergence Divergence.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    fast : int, default 12
        Span of the fast EMA.
    slow : int, default 26
        Span of the slow EMA.
    signal : int, default 9
        Span of the signal-line EMA applied to the MACD line.

    Returns
    -------
    pd.DataFrame
        Columns ``macd``, ``signal`` and ``histogram``.
    """
    fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }
    )


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average Directional Index (Wilder).

    Computes the directional movement indicators (+DI / -DI) using Wilder's
    smoothing, then the ADX as the Wilder-smoothed DX.

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    period : int, default 14
        Smoothing period.

    Returns
    -------
    pd.Series
        The ADX series. Warmup values are NaN.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=high.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=high.index,
    )

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing == EWM with alpha = 1/period.
    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr

    di_sum = plus_di + minus_di
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum.replace(0.0, np.nan)
    adx_series = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    return adx_series.rename("adx")


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """Supertrend indicator.

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    period : int, default 10
        ATR lookback period.
    multiplier : float, default 3.0
        ATR multiplier for the band offset.

    Returns
    -------
    pd.DataFrame
        Columns ``supertrend`` (the trailing stop line) and ``direction``
        (+1 for uptrend, -1 for downtrend).
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    hl2 = (high + low) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    n = len(close)
    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    st = np.full(n, np.nan)
    direction = np.full(n, np.nan)

    ub = upper_basic.to_numpy()
    lb = lower_basic.to_numpy()
    cl = close.to_numpy()

    prev_fu = np.nan
    prev_fl = np.nan
    prev_dir = 1
    prev_st = np.nan
    for i in range(n):
        if np.isnan(ub[i]):
            continue
        # First valid bar: initialise.
        if np.isnan(prev_fu):
            final_upper[i] = ub[i]
            final_lower[i] = lb[i]
            direction[i] = 1
            st[i] = final_lower[i]
        else:
            fu = ub[i] if (ub[i] < prev_fu or cl[i - 1] > prev_fu) else prev_fu
            fl = lb[i] if (lb[i] > prev_fl or cl[i - 1] < prev_fl) else prev_fl
            final_upper[i] = fu
            final_lower[i] = fl

            if prev_st == prev_fu:  # was following upper band (downtrend)
                if cl[i] > fu:
                    direction[i] = 1
                    st[i] = fl
                else:
                    direction[i] = -1
                    st[i] = fu
            else:  # was following lower band (uptrend)
                if cl[i] < fl:
                    direction[i] = -1
                    st[i] = fu
                else:
                    direction[i] = 1
                    st[i] = fl

        prev_fu = final_upper[i]
        prev_fl = final_lower[i]
        prev_dir = direction[i]
        prev_st = st[i]

    return pd.DataFrame(
        {
            "supertrend": pd.Series(st, index=close.index),
            "direction": pd.Series(direction, index=close.index),
        }
    )
