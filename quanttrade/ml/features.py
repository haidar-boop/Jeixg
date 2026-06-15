"""Feature engineering for the quanttrade ML module.

The :class:`FeatureEngineer` turns a raw OHLCV bars DataFrame into a rich,
strictly backward-looking feature matrix suitable for supervised learning, and
produces forward-looking labels for classification / regression. By construction
features only use information available *up to and including* the current bar
while labels use *future* bars, so :meth:`FeatureEngineer.build_dataset` is free
of lookahead bias once rows are aligned and NaNs are dropped.

The technical indicators are sourced from :mod:`quanttrade.indicators` when that
package is importable; otherwise simple pandas/numpy fallbacks are used so this
module always imports and works with only numpy/pandas installed.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from quanttrade.core.logging_config import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Indicator helpers: prefer the shared indicators package, fall back to pandas
# --------------------------------------------------------------------------- #
def _rsi_fallback(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd_hist_fallback(close: pd.Series) -> pd.Series:
    fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd_line = fast - slow
    signal = macd_line.ewm(span=9, adjust=False, min_periods=9).mean()
    return macd_line - signal


def _atr_fallback(high: pd.Series, low: pd.Series, close: pd.Series,
                  period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _bollinger_pctb_fallback(close: pd.Series, period: int = 20,
                             num_std: float = 2.0) -> pd.Series:
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    rng = (upper - lower).replace(0.0, np.nan)
    return (close - lower) / rng


class FeatureEngineer:
    """Build a feature matrix and labels from an OHLCV bars DataFrame.

    Parameters
    ----------
    rsi_period, atr_period, bb_period : int
        Lookback windows for the corresponding indicators.
    vol_windows : tuple[int, ...]
        Windows used for rolling realized volatility features.
    """

    def __init__(self, rsi_period: int = 14, atr_period: int = 14,
                 bb_period: int = 20, vol_windows: Tuple[int, ...] = (5, 10, 20)):
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.vol_windows = vol_windows
        self.feature_names_: list[str] = []

    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate(df: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"bars DataFrame missing columns: {sorted(missing)}")
        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a backward-looking feature DataFrame aligned to ``df.index``."""
        df = self._validate(df)
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)

        feats: dict[str, pd.Series] = {}

        # --- returns & log returns over several horizons -----------------
        for n in (1, 5, 10):
            feats[f"ret_{n}"] = close.pct_change(n)
        feats["log_ret_1"] = np.log(close / close.shift(1))

        # --- rolling realized volatility of 1-day log returns ------------
        log_ret = feats["log_ret_1"]
        for w in self.vol_windows:
            feats[f"vol_{w}"] = log_ret.rolling(w, min_periods=w).std(ddof=0)

        # --- indicator block: use indicators package when available ------
        try:
            from quanttrade.indicators import (  # type: ignore
                atr as _atr,
                bollinger_bands as _bbands,
                macd as _macd,
                rsi as _rsi,
            )
            feats["rsi"] = _rsi(close, self.rsi_period)
            feats["macd_hist"] = _macd(close)["histogram"]
            atr_series = _atr(high, low, close, self.atr_period)
            feats["bb_pctb"] = _bbands(close, self.bb_period)["percent_b"]
            logger.debug("Using quanttrade.indicators for feature engineering.")
        except Exception as exc:  # pragma: no cover - exercised when pkg absent
            logger.warning("indicators package unavailable (%s); using fallbacks.", exc)
            feats["rsi"] = _rsi_fallback(close, self.rsi_period)
            feats["macd_hist"] = _macd_hist_fallback(close)
            atr_series = _atr_fallback(high, low, close, self.atr_period)
            feats["bb_pctb"] = _bollinger_pctb_fallback(close, self.bb_period)

        # ATR normalized by price so it is comparable across instruments
        feats["atr_norm"] = atr_series / close.replace(0.0, np.nan)

        # --- volume z-score ---------------------------------------------
        vol_mean = volume.rolling(20, min_periods=20).mean()
        vol_std = volume.rolling(20, min_periods=20).std(ddof=0)
        feats["volume_z"] = (volume - vol_mean) / vol_std.replace(0.0, np.nan)

        # --- price vs SMA ratios ----------------------------------------
        for w in (10, 20, 50):
            sma = close.rolling(w, min_periods=w).mean()
            feats[f"price_sma_{w}"] = close / sma.replace(0.0, np.nan) - 1.0

        # --- momentum ----------------------------------------------------
        feats["momentum_10"] = close - close.shift(10)

        # --- calendar feature -------------------------------------------
        if isinstance(df.index, pd.DatetimeIndex):
            feats["day_of_week"] = pd.Series(df.index.dayofweek, index=df.index,
                                             dtype=float)
        else:
            feats["day_of_week"] = pd.Series(0.0, index=df.index)

        out = pd.DataFrame(feats, index=df.index)
        self.feature_names_ = list(out.columns)
        return out

    # ------------------------------------------------------------------ #
    @staticmethod
    def _forward_return(df: pd.DataFrame, horizon: int) -> pd.Series:
        close = df["close"].astype(float)
        return close.shift(-horizon) / close - 1.0

    def make_labels(self, df: pd.DataFrame, horizon: int = 5,
                    threshold: float = 0.0) -> pd.Series:
        """Binary label: 1 if forward ``horizon``-bar return > ``threshold``."""
        fwd = self._forward_return(df, horizon)
        labels = (fwd > threshold).astype("float")
        labels[fwd.isna()] = np.nan
        return labels.rename("label")

    def make_regression_labels(self, df: pd.DataFrame, horizon: int = 5) -> pd.Series:
        """Continuous label: forward ``horizon``-bar return."""
        return self._forward_return(df, horizon).rename("fwd_return")

    # ------------------------------------------------------------------ #
    def build_dataset(self, df: pd.DataFrame, horizon: int = 5,
                      threshold: float = 0.0, regression: bool = False
                      ) -> Tuple[pd.DataFrame, pd.Series]:
        """Build aligned ``(X, y)`` with no lookahead.

        Features are backward-only; labels are forward over ``horizon``. Rows
        with any NaN in features or label are dropped and the two are aligned on
        a common index.
        """
        X = self.transform(df)
        if regression:
            y = self.make_regression_labels(df, horizon)
        else:
            y = self.make_labels(df, horizon, threshold)

        combined = X.copy()
        combined["__y__"] = y
        combined = combined.replace([np.inf, -np.inf], np.nan).dropna()
        y_clean = combined.pop("__y__")
        if not regression:
            y_clean = y_clean.astype(int)
        return combined, y_clean
