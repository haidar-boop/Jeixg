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
from ..core.enums import OrderSide, OrderType, SignalType
from ..core.logging_config import get_logger
from ..data.base import MarketDataProvider
from ..models import Order, Signal
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
        history_bars: int = 200,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.data = data_provider
        self.symbols = symbols
        self.sizer = sizer or FixedRiskSizer(0.01)
        self.risk = risk_manager or RiskManager()
        self.history_bars = history_bars
        self._history: dict[str, pd.DataFrame] = {}
        self._running = False

    def start(self) -> None:
        if not self.broker.is_connected:
            self.broker.connect()
        equity = self.broker.get_account().equity
        self.risk.start_day(equity)
        self._running = True
        logger.info("TradingEngine started: %s on %s via %s",
                    self.strategy.name, self.symbols, self.broker.name)

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
        return submitted

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
