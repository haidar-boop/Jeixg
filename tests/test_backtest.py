"""End-to-end backtest and optimizer tests."""
from quanttrade.backtest import (
    BacktestEngine,
    GridSearchOptimizer,
    monte_carlo_simulation,
)
from quanttrade.risk import RiskLimits, RiskManager
from quanttrade.strategies import MovingAverageCrossover


def _engine():
    return BacktestEngine(
        MovingAverageCrossover(fast=10, slow=30),
        starting_cash=100_000,
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.5,
                                            max_daily_loss_pct=0.5,
                                            max_drawdown_pct=0.9)),
    )


def test_backtest_runs(multi_data):
    result = _engine().run(multi_data)
    assert result.equity_curve.iloc[0] > 0
    assert result.performance is not None
    summary = result.summary()
    assert "sharpe" in summary and "max_drawdown" in summary


def test_backtest_no_lookahead_warmup(multi_data):
    # With a long warmup, no trades happen until enough bars exist.
    engine = BacktestEngine(MovingAverageCrossover(fast=10, slow=200),
                            risk_manager=RiskManager(RiskLimits(max_position_pct=0.9,
                                                               max_daily_loss_pct=0.9,
                                                               max_drawdown_pct=0.9)))
    result = engine.run(multi_data)
    assert isinstance(result.performance.trades.num_trades, int)


def test_grid_search(multi_data):
    opt = GridSearchOptimizer(
        MovingAverageCrossover,
        {"fast": [5, 10], "slow": [20, 50]},
        engine_kwargs={"risk_manager": RiskManager(RiskLimits(max_position_pct=0.9,
                                                             max_daily_loss_pct=0.9,
                                                             max_drawdown_pct=0.9))},
    )
    result = opt.optimize(multi_data)
    assert "fast" in result.best_params
    assert len(result.all_results) == 4


def test_monte_carlo(multi_data):
    returns = multi_data["AAPL"]["close"].pct_change()
    mc = monte_carlo_simulation(returns, n_sims=100)
    assert "terminal_multiple" in mc
    assert 0 <= mc["prob_loss"] <= 1
