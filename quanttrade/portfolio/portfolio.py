"""Portfolio tracking.

Aggregates positions, cash and a time-stamped equity curve across one or more
accounts. Records completed round-trip :class:`Trade` objects for the journal
and feeds :mod:`quanttrade.portfolio.analytics`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..core.enums import OrderSide, PositionSide
from ..core.logging_config import get_logger
from ..models import Fill, Position, Trade
from . import analytics

logger = get_logger(__name__)


class Portfolio:
    """Tracks positions, realized/unrealized P&L and the equity curve."""

    def __init__(self, starting_cash: float = 100_000.0, account_id: str = "default") -> None:
        self.account_id = account_id
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self._equity_times: list[datetime] = []
        self._equity_values: list[float] = []
        # Track entry context per symbol for round-trip journaling.
        self._open_entry: dict[str, tuple[datetime, float, float, str]] = {}

    # --- mutation -------------------------------------------------------
    def apply_fill(self, fill: Fill, strategy: str = "", sector: str = "unknown") -> None:
        pos = self.positions.setdefault(fill.symbol, Position(symbol=fill.symbol, sector=sector))
        was_flat = abs(pos.quantity) < 1e-9

        signed = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
        closing = not was_flat and (pos.quantity > 0) != (signed > 0)

        realized = pos.apply_fill(fill.side, fill.quantity, fill.price, fill.commission)

        if fill.side == OrderSide.BUY:
            self.cash -= fill.quantity * fill.price + fill.commission
        else:
            self.cash += fill.quantity * fill.price - fill.commission

        if was_flat:
            self._open_entry[fill.symbol] = (
                fill.timestamp, fill.price, fill.quantity, strategy,
            )
        elif closing:
            self._record_trade(fill, realized, strategy)

        if abs(pos.quantity) < 1e-9:
            self.positions.pop(fill.symbol, None)
            self._open_entry.pop(fill.symbol, None)

    def _record_trade(self, fill: Fill, realized: float, strategy: str) -> None:
        entry = self._open_entry.get(fill.symbol)
        if not entry:
            return
        entry_time, entry_price, entry_qty, entry_strat = entry
        side = PositionSide.LONG if fill.side == OrderSide.SELL else PositionSide.SHORT
        self.trades.append(
            Trade(
                symbol=fill.symbol,
                side=side,
                quantity=min(entry_qty, fill.quantity),
                entry_price=entry_price,
                exit_price=fill.price,
                entry_time=entry_time,
                exit_time=fill.timestamp,
                pnl=realized,
                commission=fill.commission,
                strategy=strategy or entry_strat,
            )
        )

    def mark_to_market(self, prices: dict[str, float],
                       when: datetime | None = None) -> float:
        for sym, px in prices.items():
            if sym in self.positions:
                self.positions[sym].last_price = px
        equity = self.equity
        self._equity_times.append(when or datetime.now(timezone.utc))
        self._equity_values.append(equity)
        return equity

    # --- views ----------------------------------------------------------
    @property
    def positions_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def equity(self) -> float:
        return self.cash + self.positions_value

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def realized_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    def equity_curve(self) -> pd.Series:
        if not self._equity_values:
            return pd.Series(dtype=float)
        return pd.Series(self._equity_values, index=pd.DatetimeIndex(self._equity_times),
                         name="equity")

    def performance(self, benchmark: pd.Series | None = None) -> analytics.PerformanceReport:
        return analytics.analyze(
            self.equity_curve(),
            trade_pnls=[t.pnl for t in self.trades],
            benchmark=benchmark,
        )
