"""Live / paper trading execution engine.

Orchestrates the real-time loop that mirrors the backtester's pipeline but routes
orders to a real :class:`Broker` (paper or live):

    market data -> strategy signals -> sizing -> risk gate -> broker.submit_order
                -> portfolio/journal update -> equity monitoring

The engine is broker- and data-agnostic and supports multiple symbols. It is
designed so the *same* strategy code runs unchanged across backtest, paper and
live, differing only in the injected broker and data source.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..brokers.base import Broker
from ..core.enums import OrderSide, OrderType, PositionSide, SignalType
from ..core.logging_config import get_logger
from ..data.base import MarketDataProvider
from ..models import Order, Signal
from ..notifications import Notifier, create_notifier
from ..risk import FixedRiskSizer, PositionSizer, RiskManager
from ..strategies.base import Strategy, StrategyContext

logger = get_logger(__name__)


class TradingEngine:
    """Drives a strategy against a live/paper broker."""

    def __init__(
        self,
        strategy: Strategy,
        broker: Broker,
        data_provider: MarketDataProvider,
        symbols: list[str],
        *,
        sizer: PositionSizer | None = None,
        risk_manager: RiskManager | None = None,
        notifier: Notifier | None = None,
        history_bars: int = 200,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.data = data_provider
        self.symbols = symbols
        self.sizer = sizer or FixedRiskSizer(0.01)
        self.risk = risk_manager or RiskManager()
        self.notifier = notifier or create_notifier()
        self.history_bars = history_bars
        self._history: dict[str, pd.DataFrame] = {}
        self._last_prices: dict[str, float] = {}
        # Snapshot of broker positions {symbol: (quantity, avg_price, last_price)}
        # used to detect fills (entries/exits) for trade alerts. Broker-agnostic:
        # works whether fills are synchronous (paper) or delayed (live brokers).
        self._pos_snapshot: dict[str, tuple[float, float, float]] = {}
        self._running = False

    def start(self) -> None:
        if not self.broker.is_connected:
            self.broker.connect()
        equity = self.broker.get_account().equity
        # Seed the snapshot so pre-existing positions don't trigger fake alerts.
        self._pos_snapshot = {
            p.symbol: (p.quantity, p.avg_price, p.last_price)
            for p in self.broker.get_positions()
        }
        self.risk.start_day(equity)
        self._running = True
        logger.info("TradingEngine started: %s on %s via %s",
                    self.strategy.name, self.symbols, self.broker.name)
        self.notifier.send("QuantTrade", f"Bot started: {self.strategy.name} "
                                         f"on {','.join(self.symbols)} via {self.broker.name}")

    def stop(self) -> None:
        self._running = False
        logger.info("TradingEngine stopped")

    def on_bar(self, symbol: str, bar: pd.DataFrame) -> list[Order]:
        """Process a new bar (or window) for ``symbol`` and act on signals.

        ``bar`` should be the rolling OHLCV window ending at the latest bar.
        Returns the orders submitted as a result.
        """
        self._history[symbol] = bar
        bar.attrs["symbol"] = symbol
        price = float(bar["close"].iloc[-1])
        self._last_prices[symbol] = price

        account = self.broker.get_account()
        self.risk.update_equity(account.equity)

        positions = {p.symbol: p for p in self.broker.get_positions()}
        context = StrategyContext(positions=positions, equity=account.equity,
                                  cash=account.cash)
        if len(bar) < self.strategy.warmup:
            return []

        submitted: list[Order] = []
        for signal in self.strategy.generate_signals(bar, context):
            order = self._order_from_signal(signal, price, account.equity, positions)
            if order is None:
                continue
            decision = self.risk.check_order(order, price, account.equity, positions)
            if not decision:
                logger.info("Order blocked by risk: %s", decision.reasons)
                continue
            self.broker.submit_order(order)
            submitted.append(order)

        # Detect any fills (this symbol or others) and text the user.
        self._reconcile_and_notify()
        return submitted

    def _reconcile_and_notify(self) -> None:
        """Compare broker positions to the last snapshot and alert on changes.

        Works for any broker: a freshly opened/added position triggers an
        "opened" text; a reduced/closed position triggers a "closed" text with
        the realized profit or loss.
        """
        current = self.broker.get_positions()
        cur_map = {p.symbol: p for p in current}

        # Entries / adds: position grew (in absolute size).
        for sym, pos in cur_map.items():
            old_qty = self._pos_snapshot.get(sym, (0.0, 0.0, 0.0))[0]
            if abs(pos.quantity) > abs(old_qty) + 1e-9:
                self._notify_entry(sym, pos.side, abs(pos.quantity) - abs(old_qty),
                                   pos.avg_price)

        # Exits / reduces: position shrank or disappeared -> realized P&L.
        for sym, (old_qty, old_avg, old_last) in self._pos_snapshot.items():
            cur = cur_map.get(sym)
            cur_qty = cur.quantity if cur else 0.0
            if abs(cur_qty) < abs(old_qty) - 1e-9:
                closed = abs(old_qty) - abs(cur_qty)
                exit_price = self._last_prices.get(sym, old_last) or old_avg
                direction = 1.0 if old_qty > 0 else -1.0
                pnl = (exit_price - old_avg) * closed * direction
                self._notify_exit(sym, closed, exit_price, pnl, old_avg)

        self._pos_snapshot = {
            p.symbol: (p.quantity, p.avg_price, p.last_price) for p in current
        }

    def _notify_entry(self, symbol: str, side: PositionSide, qty: float,
                      price: float) -> None:
        verb = "BUY" if side == PositionSide.LONG else "SELL"
        self.notifier.send(
            "QuantTrade: opened",
            f"{verb} {qty:g} {symbol} @ ${price:,.2f} ({self.strategy.name})",
        )

    def _notify_exit(self, symbol: str, qty: float, exit_price: float, pnl: float,
                     entry_price: float) -> None:
        result = "WON" if pnl >= 0 else "LOST"
        sign = "+" if pnl >= 0 else "-"
        cost = entry_price * qty
        ret = pnl / cost if cost else 0.0
        self.notifier.send(
            f"QuantTrade: closed {symbol} ({result})",
            f"Sold {qty:g} {symbol} @ ${exit_price:,.2f} | "
            f"{result} {sign}${abs(pnl):,.2f} ({ret:+.2%})",
        )

    def run_once(self) -> dict[str, list[Order]]:
        """Poll the latest history for every symbol and process one step each."""
        from ..core.enums import BarInterval
        results: dict[str, list[Order]] = {}
        end = datetime.now(timezone.utc)
        start = end - pd.Timedelta(days=self.history_bars * 2)
        for symbol in self.symbols:
            bars = self.data.get_historical_bars(symbol, start, end, BarInterval.DAY_1)
            if bars.empty:
                continue
            window = bars.tail(self.history_bars)
            # Feed the latest price to a paper broker if it supports it.
            if hasattr(self.broker, "update_price"):
                self.broker.update_price(symbol, float(window["close"].iloc[-1]))
            results[symbol] = self.on_bar(symbol, window)
        return results

    def _order_from_signal(self, signal: Signal, price: float, equity: float,
                           positions: dict) -> Order | None:
        symbol = signal.symbol
        if signal.type in {SignalType.CLOSE, SignalType.SELL}:
            pos = positions.get(symbol)
            if not pos or abs(pos.quantity) < 1e-9:
                return None
            side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
            return Order(symbol=symbol, side=side, quantity=abs(pos.quantity),
                         order_type=OrderType.MARKET, strategy=self.strategy.name)
        if signal.type in {SignalType.BUY, SignalType.SCALE_IN}:
            qty = self.sizer.size(equity=equity, price=price, stop_price=signal.stop_loss)
            if qty <= 0:
                return None
            return Order(symbol=symbol, side=OrderSide.BUY, quantity=qty,
                         order_type=OrderType.MARKET, strategy=self.strategy.name,
                         metadata={"stop_loss": signal.stop_loss})
        return None
