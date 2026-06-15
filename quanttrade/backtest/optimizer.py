"""Strategy optimisation and robustness analysis.

Includes:

* :class:`GridSearchOptimizer`  -- exhaustive parameter sweep.
* :class:`GeneticOptimizer`     -- genetic-algorithm parameter search for large
  spaces where grid search is intractable.
* :func:`walk_forward_analysis` -- rolling out-of-sample validation to detect
  over-fitting.
* :func:`monte_carlo_simulation`-- bootstraps the trade/return distribution to
  estimate the spread of outcomes (drawdown / terminal-equity confidence bands).

All optimisers evaluate candidates by running the :class:`BacktestEngine`, so the
objective is a real out-of-sample-capable backtest metric, not a curve fit.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..core.logging_config import get_logger
from ..strategies.base import Strategy
from .engine import BacktestEngine

logger = get_logger(__name__)

# An objective maps a BacktestResult to a scalar to maximise.
Objective = Callable[["object"], float]


def sharpe_objective(result) -> float:
    return result.performance.sharpe


def calmar_objective(result) -> float:
    return result.performance.calmar


@dataclass
class OptimizationResult:
    best_params: dict
    best_score: float
    all_results: list[tuple[dict, float]] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        rows = [{**params, "score": score} for params, score in self.all_results]
        return pd.DataFrame(rows).sort_values("score", ascending=False)


def _run_backtest(strategy_cls: type[Strategy], params: dict,
                  data: dict[str, pd.DataFrame], engine_kwargs: dict):
    strategy = strategy_cls(**params)
    engine = BacktestEngine(strategy, **engine_kwargs)
    return engine.run(data)


class GridSearchOptimizer:
    """Exhaustive grid search over a discrete parameter space."""

    def __init__(self, strategy_cls: type[Strategy], param_grid: dict[str, list],
                 objective: Objective = sharpe_objective, engine_kwargs: dict | None = None):
        self.strategy_cls = strategy_cls
        self.param_grid = param_grid
        self.objective = objective
        self.engine_kwargs = engine_kwargs or {}

    def optimize(self, data: dict[str, pd.DataFrame]) -> OptimizationResult:
        keys = list(self.param_grid)
        combos = list(itertools.product(*self.param_grid.values()))
        logger.info("Grid search: %d combinations", len(combos))
        results: list[tuple[dict, float]] = []
        best_params, best_score = {}, -np.inf
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                score = self.objective(
                    _run_backtest(self.strategy_cls, params, data, self.engine_kwargs)
                )
            except Exception:  # noqa: BLE001
                logger.exception("Backtest failed for %s", params)
                score = -np.inf
            results.append((params, score))
            if score > best_score:
                best_params, best_score = params, score
        return OptimizationResult(best_params, best_score, results)


class GeneticOptimizer:
    """Genetic-algorithm search for large/continuous parameter spaces.

    ``param_space`` maps a name to either a list of choices or a ``(low, high)``
    tuple of ints/floats. Standard GA loop: tournament selection, uniform
    crossover, per-gene mutation, elitism.
    """

    def __init__(self, strategy_cls: type[Strategy], param_space: dict,
                 objective: Objective = sharpe_objective, *, population: int = 20,
                 generations: int = 10, mutation_rate: float = 0.2,
                 elite: int = 2, seed: int = 42, engine_kwargs: dict | None = None):
        self.strategy_cls = strategy_cls
        self.param_space = param_space
        self.objective = objective
        self.population = population
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite = elite
        self.engine_kwargs = engine_kwargs or {}
        self._rng = random.Random(seed)

    def _sample_gene(self, spec):
        """A ``tuple`` spec is a numeric ``(low, high)`` range; a ``list`` spec is
        an explicit set of discrete choices."""
        if isinstance(spec, tuple) and len(spec) == 2:
            low, high = spec
            if isinstance(low, int) and isinstance(high, int):
                return self._rng.randint(low, high)
            return self._rng.uniform(low, high)
        return self._rng.choice(list(spec))

    def _random_individual(self) -> dict:
        return {k: self._sample_gene(v) for k, v in self.param_space.items()}

    def _mutate(self, ind: dict) -> dict:
        out = dict(ind)
        for key, spec in self.param_space.items():
            if self._rng.random() < self.mutation_rate:
                out[key] = self._sample_gene(spec)
        return out

    def _crossover(self, a: dict, b: dict) -> dict:
        return {k: (a[k] if self._rng.random() < 0.5 else b[k]) for k in self.param_space}

    def _evaluate(self, ind: dict, data) -> float:
        try:
            return self.objective(
                _run_backtest(self.strategy_cls, ind, data, self.engine_kwargs)
            )
        except Exception:  # noqa: BLE001
            return -np.inf

    def optimize(self, data: dict[str, pd.DataFrame]) -> OptimizationResult:
        population = [self._random_individual() for _ in range(self.population)]
        history: list[tuple[dict, float]] = []
        best_params, best_score = {}, -np.inf

        for gen in range(self.generations):
            scored = sorted(
                ((ind, self._evaluate(ind, data)) for ind in population),
                key=lambda t: t[1], reverse=True,
            )
            history.extend(scored)
            if scored[0][1] > best_score:
                best_params, best_score = scored[0]
            logger.info("GA gen %d best=%.3f", gen, scored[0][1])

            survivors = [ind for ind, _ in scored[: self.elite]]
            while len(survivors) < self.population:
                p1 = self._tournament(scored)
                p2 = self._tournament(scored)
                survivors.append(self._mutate(self._crossover(p1, p2)))
            population = survivors
        return OptimizationResult(best_params, best_score, history)

    def _tournament(self, scored, k: int = 3) -> dict:
        contenders = self._rng.sample(scored, min(k, len(scored)))
        return max(contenders, key=lambda t: t[1])[0]


def walk_forward_analysis(strategy_cls: type[Strategy], param_grid: dict,
                          data: dict[str, pd.DataFrame], *, n_windows: int = 4,
                          train_ratio: float = 0.6, objective: Objective = sharpe_objective,
                          engine_kwargs: dict | None = None) -> pd.DataFrame:
    """Rolling walk-forward: optimise in-sample, evaluate out-of-sample.

    Splits the timeline into ``n_windows`` segments; for each, grid-searches on
    the training portion and reports the chosen params' OOS performance. Stable
    OOS results across windows indicate a robust (non-overfit) strategy.
    """
    engine_kwargs = engine_kwargs or {}
    timeline = sorted(set().union(*[df.index for df in data.values()]))
    seg_len = len(timeline) // n_windows
    rows = []
    for w in range(n_windows):
        seg = timeline[w * seg_len: (w + 1) * seg_len]
        if len(seg) < 20:
            continue
        split = int(len(seg) * train_ratio)
        train_idx, test_idx = seg[:split], seg[split:]
        train = {s: df.loc[df.index.isin(train_idx)] for s, df in data.items()}
        test = {s: df.loc[df.index.isin(test_idx)] for s, df in data.items()}

        opt = GridSearchOptimizer(strategy_cls, param_grid, objective, engine_kwargs)
        best = opt.optimize(train)
        oos = _run_backtest(strategy_cls, best.best_params, test, engine_kwargs)
        rows.append({
            "window": w,
            "best_params": best.best_params,
            "in_sample_score": round(best.best_score, 3),
            "oos_sharpe": round(oos.performance.sharpe, 3),
            "oos_return": round(oos.performance.total_return, 4),
            "oos_max_dd": round(oos.performance.max_drawdown, 4),
        })
    return pd.DataFrame(rows)


def monte_carlo_simulation(returns: pd.Series, *, n_sims: int = 1000,
                           horizon: int | None = None, seed: int = 42) -> dict:
    """Bootstrap a return series to estimate the outcome distribution.

    Resamples daily returns with replacement ``n_sims`` times to build a
    distribution of terminal equity (growth multiple) and max drawdown, returning
    summary percentiles (5/50/95) and Value-at-Risk style bands.
    """
    rng = np.random.default_rng(seed)
    r = returns.dropna().to_numpy()
    if len(r) == 0:
        return {}
    horizon = horizon or len(r)
    terminals, drawdowns = [], []
    for _ in range(n_sims):
        sample = rng.choice(r, size=horizon, replace=True)
        equity = np.cumprod(1 + sample)
        terminals.append(equity[-1])
        peak = np.maximum.accumulate(equity)
        drawdowns.append(((equity - peak) / peak).min())
    terminals = np.array(terminals)
    drawdowns = np.array(drawdowns)
    return {
        "terminal_multiple": {
            "p5": float(np.percentile(terminals, 5)),
            "median": float(np.percentile(terminals, 50)),
            "p95": float(np.percentile(terminals, 95)),
            "mean": float(terminals.mean()),
        },
        "max_drawdown": {
            "p5": float(np.percentile(drawdowns, 5)),
            "median": float(np.percentile(drawdowns, 50)),
            "worst": float(drawdowns.min()),
        },
        "prob_loss": float((terminals < 1.0).mean()),
        "n_sims": n_sims,
    }
