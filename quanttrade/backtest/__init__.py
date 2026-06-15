"""Backtesting, optimisation and robustness analysis."""
from .engine import BacktestEngine, BacktestResult
from .optimizer import (
    GeneticOptimizer,
    GridSearchOptimizer,
    OptimizationResult,
    calmar_objective,
    monte_carlo_simulation,
    sharpe_objective,
    walk_forward_analysis,
)

__all__ = [
    "BacktestEngine", "BacktestResult",
    "GridSearchOptimizer", "GeneticOptimizer", "OptimizationResult",
    "walk_forward_analysis", "monte_carlo_simulation",
    "sharpe_objective", "calmar_objective",
]
