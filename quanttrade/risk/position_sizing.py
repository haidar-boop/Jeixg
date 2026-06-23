"""Position-sizing algorithms.

Each sizer answers one question: *given account equity, a price and (optionally)
a stop / volatility / edge, how many shares should we trade?* They return a
non-negative share quantity (the caller applies side).
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod


class PositionSizer(ABC):
    @abstractmethod
    def size(self, *, equity: float, price: float, **kwargs) -> float:
        """Return a share quantity (>= 0)."""


class FixedFractionSizer(PositionSizer):
    """Allocate a fixed fraction of equity as notional exposure per position.

    ``fractional=True`` supports brokers with fractional shares (e.g. Alpaca), so
    small per-symbol budgets still buy expensive stocks.
    """

    def __init__(self, fraction: float = 0.1, fractional: bool = False) -> None:
        self.fraction = fraction
        self.fractional = fractional

    def size(self, *, equity: float, price: float, **kwargs) -> float:
        if price <= 0:
            return 0.0
        shares = (equity * self.fraction) / price
        shares = min(shares, equity / price)  # never exceed the budget
        return round(shares, 4) if self.fractional else math.floor(shares)


class FixedRiskSizer(PositionSizer):
    """Risk a fixed fraction of equity *per trade*, defined by the stop distance.

    shares = (equity * risk_pct) / |entry - stop|

    With ``fractional=True`` (for brokers that support fractional shares, like
    Alpaca) the quantity isn't floored to whole shares -- important for small
    accounts where a whole share would exceed the budget.
    """

    def __init__(self, risk_pct: float = 0.01, fractional: bool = False) -> None:
        self.risk_pct = risk_pct
        self.fractional = fractional

    def size(self, *, equity: float, price: float, stop_price: float | None = None,
             **kwargs) -> float:
        if not stop_price or price <= 0:
            return 0.0
        risk_per_share = abs(price - stop_price)
        if risk_per_share <= 0:
            return 0.0
        shares = (equity * self.risk_pct) / risk_per_share
        # Never let a single position exceed the available budget.
        shares = min(shares, equity / price)
        return round(shares, 4) if self.fractional else math.floor(shares)


class VolatilitySizer(PositionSizer):
    """Volatility-targeted sizing: scale exposure so each position contributes a
    target annualised volatility (a.k.a. risk parity per position).

    shares = (equity * target_vol) / (price * asset_vol)
    """

    def __init__(self, target_vol: float = 0.15) -> None:
        self.target_vol = target_vol

    def size(self, *, equity: float, price: float, volatility: float | None = None,
             **kwargs) -> float:
        if not volatility or volatility <= 0 or price <= 0:
            return 0.0
        return math.floor((equity * self.target_vol) / (price * volatility))


class KellySizer(PositionSizer):
    """Kelly-criterion sizing from win-rate and payoff ratio.

    f* = W - (1 - W) / R, where W = win prob, R = avg_win/avg_loss.
    A ``kelly_fraction`` multiplier supports the common 'fractional Kelly'.
    """

    def __init__(self, kelly_fraction: float = 0.5) -> None:
        self.kelly_fraction = kelly_fraction

    @staticmethod
    def kelly_fraction_value(win_rate: float, payoff_ratio: float) -> float:
        if payoff_ratio <= 0:
            return 0.0
        f = win_rate - (1.0 - win_rate) / payoff_ratio
        return max(f, 0.0)

    def size(self, *, equity: float, price: float, win_rate: float = 0.5,
             payoff_ratio: float = 1.0, **kwargs) -> float:
        if price <= 0:
            return 0.0
        f = self.kelly_fraction_value(win_rate, payoff_ratio) * self.kelly_fraction
        return math.floor((equity * f) / price)


SIZERS = {
    "fixed_fraction": FixedFractionSizer,
    "fixed_risk": FixedRiskSizer,
    "volatility": VolatilitySizer,
    "kelly": KellySizer,
}


def create_sizer(name: str, **kwargs) -> PositionSizer:
    if name not in SIZERS:
        raise ValueError(f"Unknown sizer '{name}'. Available: {list(SIZERS)}")
    return SIZERS[name](**kwargs)
