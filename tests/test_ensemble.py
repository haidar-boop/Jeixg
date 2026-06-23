"""Tests for the ensemble allocator + portfolio rebalancing engine."""
from datetime import datetime

from quanttrade.brokers import PaperBroker
from quanttrade.data import create_data_provider
from quanttrade.execution.portfolio_engine import PortfolioEngine
from quanttrade.notifications import Notifier
from quanttrade.risk import RiskLimits, RiskManager
from quanttrade.strategies.ensemble import EnsembleAllocator

UNIVERSE = ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "JPM", "XOM", "WMT", "SPY", "QQQ"]


class _Quiet(Notifier):
    name = "q"
    def _send(self, s, m): ...


def _bars():
    prov = create_data_provider("synthetic")
    return prov.get_multiple(UNIVERSE, datetime(2019, 1, 1), datetime(2023, 1, 1))


def test_allocator_weights_are_long_only_and_bounded():
    rows = EnsembleAllocator().detail(_bars())
    assert rows, "allocator returned no rows"
    weights = [r["weight"] for r in rows]
    assert all(w >= 0 for w in weights)          # long-only
    assert sum(weights) <= 1.01                   # never more than fully invested


def test_portfolio_engine_rebalances_within_cap():
    broker = PaperBroker(starting_cash=100_000, commission_per_share=0, slippage_bps=0)
    broker.connect()
    eng = PortfolioEngine(
        broker, create_data_provider("synthetic"), UNIVERSE,
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.5, max_gross_exposure_pct=3.0)),
        notifier=_Quiet(), max_capital=1000)
    eng.start()
    res = eng.run_once()
    assert res["rebalanced"] is True
    deployed = sum(abs(p.market_value) for p in broker.get_positions())
    assert deployed <= 1050                        # within the $1000 cap
    # Same day -> no second rebalance.
    assert eng.run_once()["rebalanced"] is False


def test_portfolio_engine_flatten():
    broker = PaperBroker(starting_cash=100_000, commission_per_share=0, slippage_bps=0)
    broker.connect()
    eng = PortfolioEngine(broker, create_data_provider("synthetic"), UNIVERSE,
                          notifier=_Quiet(), max_capital=1000)
    eng.start()
    eng.run_once()
    assert eng.flatten_all() >= 0
    assert broker.get_positions() == []


def test_allocator_survives_bad_tickers():
    """One empty/short/NaN ticker must not wipe the whole basket (regression)."""
    import numpy as np
    import pandas as pd
    bars = _bars()
    bars["BADX"] = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])  # empty
    bars["NEWY"] = bars["AAPL"].tail(20).copy()                                      # too short
    g = bars["XOM"].copy(); g.loc[g.index[-1], "close"] = np.nan; bars["XOM"] = g    # NaN tail
    rows = EnsembleAllocator().detail(bars)
    syms = {r["symbol"] for r in rows}
    assert len(rows) >= 6
    assert "BADX" not in syms and "NEWY" not in syms
