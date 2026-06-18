"""Trading strategy framework and built-in strategies.

Importing this package registers all built-in strategies with the
``StrategyRegistry`` so they can be created by name (config-driven / plug-in).
"""
from .base import Strategy, StrategyContext, StrategyRegistry, register_strategy
from .mean_reversion import BollingerReversion, RSIReversion
from .momentum import Breakout, Momentum, TrendMomentum, TrendPullback
from .trend_following import MovingAverageCrossover, TrendStrength

__all__ = [
    "Strategy",
    "StrategyContext",
    "StrategyRegistry",
    "register_strategy",
    "MovingAverageCrossover",
    "TrendStrength",
    "BollingerReversion",
    "RSIReversion",
    "Momentum",
    "TrendMomentum",
    "TrendPullback",
    "Breakout",
]
