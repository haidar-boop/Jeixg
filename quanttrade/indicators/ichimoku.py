"""Ichimoku Kinko Hyo (Ichimoku Cloud)."""

from __future__ import annotations

import pandas as pd

__all__ = ["ichimoku"]


def ichimoku(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
) -> pd.DataFrame:
    """Ichimoku Cloud components.

    Conventions:

    - ``tenkan_sen`` (conversion line): midpoint of the high/low over
      ``tenkan`` periods.
    - ``kijun_sen`` (base line): midpoint of the high/low over ``kijun``
      periods.
    - ``senkou_a`` (leading span A): average of tenkan and kijun, plotted
      ``kijun`` periods ahead.
    - ``senkou_b`` (leading span B): midpoint of the high/low over
      ``senkou_b`` periods, plotted ``kijun`` periods ahead.
    - ``chikou_span`` (lagging span): close plotted ``kijun`` periods back.

    The leading spans are shifted forward (positive shift), which extends the
    index into the future -- this is the standard, non-lookahead display
    convention. The lagging span is shifted backward.

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    tenkan : int, default 9
        Conversion-line period.
    kijun : int, default 26
        Base-line period and displacement.
    senkou_b : int, default 52
        Leading span B period.

    Returns
    -------
    pd.DataFrame
        Columns ``tenkan_sen``, ``kijun_sen``, ``senkou_a``, ``senkou_b`` and
        ``chikou_span``.
    """

    def _midpoint(period: int) -> pd.Series:
        highest = high.rolling(window=period, min_periods=period).max()
        lowest = low.rolling(window=period, min_periods=period).min()
        return (highest + lowest) / 2.0

    tenkan_sen = _midpoint(tenkan)
    kijun_sen = _midpoint(kijun)
    senkou_a = ((tenkan_sen + kijun_sen) / 2.0).shift(kijun)
    senkou_b_line = _midpoint(senkou_b).shift(kijun)
    chikou_span = close.shift(-kijun)

    return pd.DataFrame(
        {
            "tenkan_sen": tenkan_sen,
            "kijun_sen": kijun_sen,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b_line,
            "chikou_span": chikou_span,
        }
    )
