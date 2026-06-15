"""Broker abstraction.

Every broker (paper, Alpaca, IBKR, Tradier, ...) implements this interface, so
strategies and the execution engine are broker-agnostic. The contract covers
connection lifecycle, order management and account/position queries.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import AccountSnapshot, Order, Position, Quote


class Broker(ABC):
    """Abstract trading-broker interface."""

    name: str = "base"
    supports_fractional: bool = False
    supports_shorting: bool = True

    # --- lifecycle ------------------------------------------------------
    @abstractmethod
    def connect(self) -> None:
        """Establish/authenticate the broker session."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the broker session."""

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    # --- order management ----------------------------------------------
    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order. Returns the updated order with broker id/status."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None: ...

    @abstractmethod
    def get_open_orders(self) -> list[Order]: ...

    # --- account / positions -------------------------------------------
    @abstractmethod
    def get_account(self) -> AccountSnapshot: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    def get_position(self, symbol: str) -> Position | None:
        for pos in self.get_positions():
            if pos.symbol == symbol:
                return pos
        return None

    # --- pricing (optional; backtest/paper inject prices) --------------
    def get_quote(self, symbol: str) -> Quote | None:  # pragma: no cover - optional
        return None

    def __enter__(self) -> "Broker":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()
