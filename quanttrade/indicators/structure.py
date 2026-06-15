"""Market-structure tools: swing points, support/resistance, trend and breakouts.

All series-returning functions are aligned to the input index and avoid
lookahead bias for *trading* signals: ``detect_trend`` and ``detect_breakout``
use only information available up to and including the current bar. The
``swing_highs_lows`` detector is, by definition, a centered pattern detector
(it needs ``lookback`` bars on each side to confirm a pivot), so its flags are
only set on bars that have enough future bars to confirm -- this is the
standard meaning of a confirmed swing point and is intended for analysis /
labelling rather than as a real-time entry trigger.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "swing_highs_lows",
    "support_resistance",
    "detect_trend",
    "detect_breakout",
]


def swing_highs_lows(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 5,
) -> pd.DataFrame:
    """Detect confirmed swing highs and swing lows (fractal pivots).

    A bar is a swing high if its high is the maximum of the window spanning
    ``lookback`` bars before and ``lookback`` bars after it; symmetrically for
    swing lows with the minimum low.

    Parameters
    ----------
    high, low : pd.Series
        Price series sharing the same index.
    lookback : int, default 5
        Number of bars on each side used to confirm a pivot.

    Returns
    -------
    pd.DataFrame
        Boolean columns ``swing_high`` and ``swing_low`` aligned to the input
        index. Bars without enough neighbours on both sides are ``False``.
    """
    window = 2 * lookback + 1
    # Centered rolling max/min: the value at position i compared against the
    # window [i - lookback, i + lookback].
    centered_high_max = high.rolling(window=window, center=True, min_periods=window).max()
    centered_low_min = low.rolling(window=window, center=True, min_periods=window).min()

    swing_high = (high == centered_high_max) & centered_high_max.notna()
    swing_low = (low == centered_low_min) & centered_low_min.notna()

    return pd.DataFrame(
        {
            "swing_high": swing_high.fillna(False).astype(bool),
            "swing_low": swing_low.fillna(False).astype(bool),
        }
    )


def support_resistance(
    close: pd.Series,
    window: int = 20,
    tolerance: float = 0.02,
) -> dict[str, list[float]]:
    """Identify support and resistance levels by clustering local extrema.

    Local maxima / minima of ``close`` are found using a centered rolling
    window of size ``2 * window + 1``. Nearby extrema (within ``tolerance`` of
    each other, measured as a fraction of price) are clustered together and
    each cluster is reduced to its mean level.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    window : int, default 20
        Half-width of the window used to detect local extrema.
    tolerance : float, default 0.02
        Relative distance (e.g. ``0.02`` == 2%) within which two extrema are
        considered the same level.

    Returns
    -------
    dict[str, list[float]]
        ``{"support": [...], "resistance": [...]}`` with clustered price
        levels sorted ascending.
    """
    span = 2 * window + 1
    roll_max = close.rolling(window=span, center=True, min_periods=span).max()
    roll_min = close.rolling(window=span, center=True, min_periods=span).min()

    resistance_points = close[(close == roll_max) & roll_max.notna()].to_numpy()
    support_points = close[(close == roll_min) & roll_min.notna()].to_numpy()

    def _cluster(points: np.ndarray) -> list[float]:
        if points.size == 0:
            return []
        ordered = np.sort(points.astype(float))
        clusters: list[list[float]] = [[float(ordered[0])]]
        for value in ordered[1:]:
            anchor = clusters[-1][0]
            # Relative gap from the cluster's first (lowest) member.
            denom = abs(anchor) if anchor != 0 else 1.0
            if (value - anchor) / denom <= tolerance:
                clusters[-1].append(float(value))
            else:
                clusters.append([float(value)])
        return [float(np.mean(c)) for c in clusters]

    return {
        "support": _cluster(support_points),
        "resistance": _cluster(resistance_points),
    }


def detect_trend(close: pd.Series, period: int = 50) -> pd.Series:
    """Classify the prevailing trend over a rolling window.

    For each bar the slope of an ordinary-least-squares line fit to the last
    ``period`` closes is computed. The slope is normalised by the mean price
    of the window to make the threshold scale-free. A normalised slope above a
    small positive threshold is an uptrend, below the negative threshold a
    downtrend, otherwise sideways.

    Only past data (the trailing window ending at the current bar) is used, so
    there is no lookahead bias.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 50
        Rolling regression window length.

    Returns
    -------
    pd.Series
        Strings ``"uptrend"``, ``"downtrend"`` or ``"sideways"``. Warmup bars
        (before ``period`` observations exist) are ``"sideways"``.
    """
    x = np.arange(period, dtype=float)
    x_mean = x.mean()
    x_centered = x - x_mean
    x_var = float(np.dot(x_centered, x_centered))

    # Threshold on slope-per-bar as a fraction of price level.
    threshold = 0.0005

    def _slope_label(window: np.ndarray) -> float:
        y_mean = window.mean()
        slope = float(np.dot(x_centered, window - y_mean) / x_var)
        norm = slope / y_mean if y_mean != 0 else 0.0
        if norm > threshold:
            return 1.0
        if norm < -threshold:
            return -1.0
        return 0.0

    codes = close.rolling(window=period, min_periods=period).apply(_slope_label, raw=True)
    mapping = {1.0: "uptrend", -1.0: "downtrend", 0.0: "sideways"}
    result = codes.map(mapping)
    return result.fillna("sideways").rename("trend")


def detect_breakout(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 20,
) -> pd.Series:
    """Detect price breakouts of a recent high/low channel.

    The channel is defined by the highest high and lowest low of the *prior*
    ``window`` bars (the current bar is excluded via a shift, avoiding
    lookahead). A close above the prior highest high is ``"breakout_up"``; a
    close below the prior lowest low is ``"breakout_down"``; otherwise
    ``"none"``.

    Parameters
    ----------
    high, low, close : pd.Series
        Price series sharing the same index.
    window : int, default 20
        Channel lookback length.

    Returns
    -------
    pd.Series
        Strings ``"breakout_up"``, ``"breakout_down"`` or ``"none"``.
    """
    prior_high = high.rolling(window=window, min_periods=window).max().shift(1)
    prior_low = low.rolling(window=window, min_periods=window).min().shift(1)

    up = close > prior_high
    down = close < prior_low

    result = pd.Series("none", index=close.index, dtype=object)
    result = result.mask(up, "breakout_up")
    result = result.mask(down, "breakout_down")
    # Where the channel is undefined (warmup), report "none".
    undefined = prior_high.isna() | prior_low.isna()
    result = result.mask(undefined, "none")
    return result.rename("breakout")
