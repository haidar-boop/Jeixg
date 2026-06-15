"""Volume-based indicators: OBV, VWAP, Volume Profile, MFI and A/D line."""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "obv",
    "vwap",
    "volume_profile",
    "mfi",
    "accumulation_distribution",
]


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume.

    Adds the period's volume when the close rises and subtracts it when the
    close falls, accumulating the running total.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    volume : pd.Series
        Volume series sharing the same index.

    Returns
    -------
    pd.Series
        Cumulative OBV series.
    """
    direction = np.sign(close.diff()).fillna(0.0)
    signed_volume = direction * volume
    return signed_volume.cumsum().rename("obv")


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Cumulative (session) Volume-Weighted Average Price.

    Uses the typical price ``(high + low + close) / 3`` weighted by volume,
    accumulated from the start of the series.

    Parameters
    ----------
    high, low, close, volume : pd.Series
        Price and volume series sharing the same index.

    Returns
    -------
    pd.Series
        Running VWAP.
    """
    typical_price = (high + low + close) / 3.0
    cum_pv = (typical_price * volume).cumsum()
    cum_vol = volume.cumsum().replace(0.0, np.nan)
    return (cum_pv / cum_vol).rename("vwap")


def volume_profile(
    close: pd.Series,
    volume: pd.Series,
    bins: int = 20,
) -> pd.DataFrame:
    """Volume-at-price histogram (volume profile).

    Buckets the close prices into ``bins`` evenly spaced price levels and sums
    the volume traded within each bucket. The Point of Control (POC) -- the
    price level with the most volume -- is flagged in the ``is_poc`` column.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    volume : pd.Series
        Volume series sharing the same index.
    bins : int, default 20
        Number of price buckets.

    Returns
    -------
    pd.DataFrame
        Columns ``price_level`` (bucket midpoint), ``volume`` (volume at that
        price) and ``is_poc`` (boolean marking the Point of Control). Indexed
        0..bins-1 from lowest to highest price.
    """
    valid = close.notna() & volume.notna()
    prices = close[valid].to_numpy()
    vols = volume[valid].to_numpy()

    if prices.size == 0:
        return pd.DataFrame(columns=["price_level", "volume", "is_poc"])

    low = float(prices.min())
    high = float(prices.max())
    if high == low:
        # Degenerate: all volume at a single price.
        return pd.DataFrame(
            {"price_level": [low], "volume": [float(vols.sum())], "is_poc": [True]}
        )

    edges = np.linspace(low, high, bins + 1)
    hist, _ = np.histogram(prices, bins=edges, weights=vols)
    midpoints = (edges[:-1] + edges[1:]) / 2.0

    poc_idx = int(np.argmax(hist))
    is_poc = np.zeros(bins, dtype=bool)
    is_poc[poc_idx] = True

    return pd.DataFrame(
        {
            "price_level": midpoints,
            "volume": hist,
            "is_poc": is_poc,
        }
    )


def mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Money Flow Index.

    A volume-weighted RSI built on the typical price.

    Parameters
    ----------
    high, low, close, volume : pd.Series
        Price and volume series sharing the same index.
    period : int, default 14
        Lookback period.

    Returns
    -------
    pd.Series
        MFI values in [0, 100]. Warmup values are NaN.
    """
    typical_price = (high + low + close) / 3.0
    raw_money_flow = typical_price * volume
    tp_change = typical_price.diff()

    positive_flow = raw_money_flow.where(tp_change > 0, 0.0)
    negative_flow = raw_money_flow.where(tp_change < 0, 0.0)

    pos_sum = positive_flow.rolling(window=period, min_periods=period).sum()
    neg_sum = negative_flow.rolling(window=period, min_periods=period).sum()

    money_ratio = pos_sum / neg_sum.replace(0.0, np.nan)
    mfi_series = 100.0 - (100.0 / (1.0 + money_ratio))
    # If there is no negative flow, MFI is 100.
    mfi_series = mfi_series.where(neg_sum != 0.0, 100.0)
    mfi_series = mfi_series.where(pos_sum.notna())
    return mfi_series.rename("mfi")


def accumulation_distribution(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Accumulation / Distribution line.

    Parameters
    ----------
    high, low, close, volume : pd.Series
        Price and volume series sharing the same index.

    Returns
    -------
    pd.Series
        Cumulative A/D line.
    """
    rng = (high - low).replace(0.0, np.nan)
    money_flow_multiplier = ((close - low) - (high - close)) / rng
    money_flow_multiplier = money_flow_multiplier.fillna(0.0)
    money_flow_volume = money_flow_multiplier * volume
    return money_flow_volume.cumsum().rename("accumulation_distribution")
