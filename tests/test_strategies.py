"""Tests for the strategy framework and built-in strategies."""
import pandas as pd

from quanttrade.models import Signal
from quanttrade.strategies import (
    BollingerReversion,
    MovingAverageCrossover,
    StrategyRegistry,
)
from quanttrade.strategies.base import StrategyContext


def test_registry_has_builtins():
    available = StrategyRegistry.available()
    assert "ma_crossover" in available
    assert "bollinger_reversion" in available


def test_registry_create():
    strat = StrategyRegistry.create("ma_crossover", fast=5, slow=20)
    assert isinstance(strat, MovingAverageCrossover)
    assert strat.fast == 5


def test_strategy_returns_signals(ohlcv):
    strat = MovingAverageCrossover(fast=10, slow=30)
    ohlcv.attrs["symbol"] = "AAPL"
    ctx = StrategyContext(positions={}, equity=100_000, cash=100_000)
    signals = strat.generate_signals(ohlcv, ctx)
    assert all(isinstance(s, Signal) for s in signals)


def test_warmup_returns_empty():
    strat = MovingAverageCrossover(fast=10, slow=50)
    short = pd.DataFrame({"open": [1, 2], "high": [1, 2], "low": [1, 2],
                          "close": [1, 2], "volume": [1, 2]})
    short.attrs["symbol"] = "X"
    ctx = StrategyContext()
    assert strat.generate_signals(short, ctx) == []


def test_context_position_helpers():
    from quanttrade.models import Position
    ctx = StrategyContext(positions={"AAPL": Position("AAPL", quantity=10)})
    assert ctx.has_position("AAPL")
    assert ctx.position_qty("AAPL") == 10
    assert not ctx.has_position("MSFT")


def test_trend_momentum_registered_and_signals(ohlcv):
    strat = StrategyRegistry.create("trend_momentum", trend_ma=50, lookback=30)
    ohlcv.attrs["symbol"] = "AAPL"
    ctx = StrategyContext(positions={}, equity=100_000, cash=100_000)
    signals = strat.generate_signals(ohlcv, ctx)
    assert all(isinstance(s, Signal) for s in signals)
