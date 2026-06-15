"""Example: optimisation + robustness analysis.

Runs a grid search, a genetic search, a walk-forward analysis and a Monte-Carlo
simulation on a single strategy. Run:

    python examples/optimize_strategy.py
"""
from datetime import datetime

from quanttrade.backtest import (
    GeneticOptimizer,
    GridSearchOptimizer,
    monte_carlo_simulation,
    walk_forward_analysis,
)
from quanttrade.data import create_data_provider
from quanttrade.risk import RiskLimits, RiskManager
from quanttrade.strategies import MovingAverageCrossover

# Relaxed risk so the optimiser can explore freely (tighten for production).
ENGINE_KWARGS = {
    "risk_manager": RiskManager(RiskLimits(
        max_position_pct=0.9, max_daily_loss_pct=0.9, max_drawdown_pct=0.9,
    )),
}


def main() -> None:
    provider = create_data_provider("synthetic")
    data = {"SPY": provider.get_historical_bars("SPY", datetime(2015, 1, 1),
                                                datetime(2023, 1, 1))}

    print("== Grid search ==")
    grid = GridSearchOptimizer(
        MovingAverageCrossover,
        {"fast": [10, 20, 30], "slow": [50, 100, 200]},
        engine_kwargs=ENGINE_KWARGS,
    )
    gres = grid.optimize(data)
    print("best:", gres.best_params, "sharpe:", round(gres.best_score, 3))

    print("\n== Genetic search ==")
    ga = GeneticOptimizer(
        MovingAverageCrossover,
        {"fast": (5, 40), "slow": (50, 250)},
        population=12, generations=5, engine_kwargs=ENGINE_KWARGS,
    )
    ga_res = ga.optimize(data)
    print("best:", ga_res.best_params, "sharpe:", round(ga_res.best_score, 3))

    print("\n== Walk-forward analysis ==")
    wf = walk_forward_analysis(
        MovingAverageCrossover,
        {"fast": [10, 20], "slow": [50, 100]},
        data, n_windows=4, engine_kwargs=ENGINE_KWARGS,
    )
    print(wf.to_string(index=False))

    print("\n== Monte-Carlo simulation ==")
    returns = data["SPY"]["close"].pct_change()
    mc = monte_carlo_simulation(returns, n_sims=1000)
    print("terminal multiple (p5/median/p95):",
          round(mc["terminal_multiple"]["p5"], 2),
          round(mc["terminal_multiple"]["median"], 2),
          round(mc["terminal_multiple"]["p95"], 2))
    print("probability of loss:", round(mc["prob_loss"], 3))


if __name__ == "__main__":
    main()
