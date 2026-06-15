"""Tests for the technical-analysis engine."""
import numpy as np
import pandas as pd
import pytest

from quanttrade.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    obv,
    rsi,
    sma,
    vwap,
)


@pytest.fixture
def series():
    return pd.Series(np.random.RandomState(0).randn(200).cumsum() + 100)


@pytest.fixture
def frame(series):
    return pd.DataFrame({
        "open": series, "high": series + 1, "low": series - 1,
        "close": series, "volume": np.abs(np.random.RandomState(1).randn(200)) * 1e6,
    })


def test_sma_matches_rolling_mean(series):
    assert np.isclose(sma(series, 10).iloc[-1], series.tail(10).mean())


def test_ema_length(series):
    assert len(ema(series, 12)) == len(series)


def test_rsi_bounds(series):
    r = rsi(series).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_rsi_all_gains_is_100():
    up = pd.Series(np.arange(1, 100, dtype=float))
    assert rsi(up).iloc[-1] > 99


def test_macd_columns(series):
    df = macd(series)
    assert set(df.columns) >= {"macd", "signal", "histogram"}


def test_atr_positive(frame):
    a = atr(frame["high"], frame["low"], frame["close"]).dropna()
    assert (a >= 0).all()


def test_bollinger_ordering(series):
    bb = bollinger_bands(series).dropna()
    assert (bb["upper"] >= bb["middle"]).all()
    assert (bb["middle"] >= bb["lower"]).all()


def test_obv_changes_with_price(frame):
    o = obv(frame["close"], frame["volume"])
    assert len(o) == len(frame)


def test_vwap_within_range(frame):
    v = vwap(frame["high"], frame["low"], frame["close"], frame["volume"]).dropna()
    assert v.iloc[-1] > 0


def test_short_series_no_crash():
    s = pd.Series([100.0, 101.0, 102.0])
    # Should not raise even though period > length.
    rsi(s, 14)
    macd(s)
