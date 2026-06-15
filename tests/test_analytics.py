"""Tests for performance analytics."""
import numpy as np
import pandas as pd
import pytest

from quanttrade.portfolio import analytics


def _curve(values):
    idx = pd.date_range("2022-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


def test_max_drawdown():
    curve = _curve([100, 120, 90, 110])
    # Peak 120 -> trough 90 = -25%.
    assert analytics.max_drawdown(curve) == pytest.approx(-0.25)


def test_sharpe_zero_for_constant():
    curve = _curve([100] * 50)
    assert analytics.sharpe_ratio(curve.pct_change().dropna()) == 0.0


def test_sharpe_positive_for_uptrend():
    rng = np.random.RandomState(0)
    rets = pd.Series(rng.normal(0.001, 0.005, 252))
    assert analytics.sharpe_ratio(rets) > 0


def test_trade_statistics():
    stats = analytics.trade_statistics([100, -50, 200, -30, 80])
    assert stats.num_trades == 5
    assert stats.win_rate == pytest.approx(0.6)
    assert stats.avg_win == pytest.approx((100 + 200 + 80) / 3)


def test_alpha_beta_perfect_correlation():
    rng = np.random.RandomState(1)
    bench = pd.Series(rng.normal(0, 0.01, 200))
    strat = bench * 1.5  # beta should be ~1.5, alpha ~0
    alpha, beta = analytics.alpha_beta(strat, bench)
    assert beta == pytest.approx(1.5, abs=1e-6)
    assert alpha == pytest.approx(0.0, abs=1e-6)


def test_full_report():
    rng = np.random.RandomState(2)
    curve = _curve(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 252)))
    report = analytics.analyze(curve, trade_pnls=[10, -5, 20])
    assert report.trades.num_trades == 3
    assert -1 <= report.max_drawdown <= 0
    assert isinstance(report.sharpe, float)
