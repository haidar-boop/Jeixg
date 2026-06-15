"""Tests for risk management and position sizing."""
import pytest

from quanttrade.core.enums import OrderSide
from quanttrade.models import Order, Position
from quanttrade.risk import (
    FixedRiskSizer,
    KellySizer,
    RiskLimits,
    RiskManager,
    VolatilitySizer,
)


def test_fixed_risk_sizer():
    sizer = FixedRiskSizer(risk_pct=0.01)
    # Risk $1000 (1% of 100k), stop 2 away -> 500 shares.
    qty = sizer.size(equity=100_000, price=100, stop_price=98)
    assert qty == 500


def test_fixed_risk_no_stop_returns_zero():
    assert FixedRiskSizer().size(equity=100_000, price=100) == 0


def test_volatility_sizer():
    qty = VolatilitySizer(target_vol=0.15).size(equity=100_000, price=100, volatility=0.30)
    assert qty == 500  # 100k*0.15 / (100*0.30) = 15000 / 30


def test_kelly_fraction():
    f = KellySizer.kelly_fraction_value(win_rate=0.6, payoff_ratio=2.0)
    assert f == pytest.approx(0.4)  # 0.6 - 0.4/2


def test_position_cap_blocks_oversized_order():
    rm = RiskManager(RiskLimits(max_position_pct=0.10))
    rm.start_day(100_000)
    order = Order("AAPL", OrderSide.BUY, quantity=200)  # 200*100=20k = 20% > 10%
    decision = rm.check_order(order, 100.0, 100_000, {})
    assert not decision
    assert any("position cap" in r for r in decision.reasons)


def test_position_within_cap_allowed():
    rm = RiskManager(RiskLimits(max_position_pct=0.10, max_gross_exposure_pct=2.0))
    rm.start_day(100_000)
    order = Order("AAPL", OrderSide.BUY, quantity=50)  # 5k = 5%
    assert rm.check_order(order, 100.0, 100_000, {})


def test_daily_loss_halt():
    rm = RiskManager(RiskLimits(max_daily_loss_pct=0.03))
    rm.start_day(100_000)
    rm.update_equity(96_000)  # -4% > 3%
    assert rm.halted
    order = Order("AAPL", OrderSide.BUY, quantity=1)
    assert not rm.check_order(order, 100.0, 96_000, {})


def test_drawdown_halt():
    rm = RiskManager(RiskLimits(max_drawdown_pct=0.20, max_daily_loss_pct=1.0))
    rm.start_day(100_000)
    rm.update_equity(120_000)  # new high-water mark
    rm.update_equity(95_000)   # -20.8% from peak
    assert rm.halted


def test_gross_exposure_cap():
    rm = RiskManager(RiskLimits(max_position_pct=1.0, max_gross_exposure_pct=1.0))
    rm.start_day(100_000)
    positions = {"MSFT": Position("MSFT", quantity=900, avg_price=100, last_price=100)}
    order = Order("AAPL", OrderSide.BUY, quantity=200)  # 20k + 90k = 110k > 100k
    decision = rm.check_order(order, 100.0, 100_000, positions)
    assert not decision
    assert any("gross exposure" in r for r in decision.reasons)
