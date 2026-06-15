"""Strategy framework.

A strategy consumes a rolling window of market data and emits :class:`Signal`
objects. Strategies are pure decision-makers -- they never place orders directly.
Sizing and execution are delegated to the risk manager and execution engine,
which keeps strategies testable and reusable across backtest / paper / live.

Plug-in model: subclass :class:`Strategy`, register with ``@register_strategy``
or via :func:`StrategyRegistry.register`, and reference it by name in config.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

import pandas as pd

from ..core.logging_config import get_logger
from ..models import Signal

logger = get_logger(__name__)


class StrategyContext:
    """Read-only view passed to strategies at decision time.

    Exposes current positions and account state without giving the strategy the
    ability to mutate them (separation of concerns).
    """

    def __init__(self, positions: dict[str, Any] | None = None,
                 equity: float = 0.0, cash: float = 0.0) -> None:
        self.positions = positions or {}
        self.equity = equity
        self.cash = cash

    def position_qty(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        return getattr(pos, "quantity", 0.0) if pos else 0.0

    def has_position(self, symbol: str) -> bool:
        return abs(self.position_qty(symbol)) > 1e-9


class Strategy(ABC):
    """Base class for all trading strategies."""

    #: Minimum number of bars required before the strategy can produce signals.
    warmup: int = 1

    def __init__(self, name: str | None = None, **params: Any) -> None:
        self.name = name or self.__class__.__name__
        self.params = params
        self.on_init()

    def on_init(self) -> None:
        """Hook for subclasses to validate/derive parameters."""

    @abstractmethod
    def generate_signals(
        self, data: pd.DataFrame, context: StrategyContext
    ) -> list[Signal]:
        """Return signals given a window of OHLCV data for one symbol.

        ``data`` is indexed by timestamp with at least an OHLCV schema; the last
        row is the most recent (decision) bar.
        """

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.name} {self.params}>"


class StrategyRegistry:
    """Registry enabling config-driven strategy instantiation (plug-ins)."""

    _registry: dict[str, type[Strategy]] = {}

    @classmethod
    def register(cls, name: str, strategy_cls: type[Strategy]) -> None:
        cls._registry[name.lower()] = strategy_cls

    @classmethod
    def create(cls, name: str, **params: Any) -> Strategy:
        key = name.lower()
        if key not in cls._registry:
            raise KeyError(f"Unknown strategy '{name}'. Available: {cls.available()}")
        return cls._registry[key](**params)

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._registry)


def register_strategy(name: str) -> Callable[[type[Strategy]], type[Strategy]]:
    """Class decorator to register a strategy plug-in."""

    def deco(strategy_cls: type[Strategy]) -> type[Strategy]:
        StrategyRegistry.register(name, strategy_cls)
        return strategy_cls

    return deco
