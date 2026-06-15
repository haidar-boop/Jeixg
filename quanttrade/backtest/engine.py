"""Event-driven backtesting engine.

Drives the full decision pipeline bar-by-bar over historical data:

    data window -> strategy.generate_signals -> position sizing -> risk gate
                -> simulated fill (slippage + commission) -> portfolio accounting

Design choices that avoid common backtest pitfalls:

* **No lookahead** -- a strategy only ever sees data up to and including the
  current bar; fills occur at that bar's close adjusted for slippage.
* **Single accounting authority** -- the :class:`Portfolio` owns cash, positions,
  the trade journal and the equity curve, so backtest and live share logic.
* **Risk integrated** -- every order passes the :class:`RiskManager` gate and the
  equity curve is monitored for daily-loss / drawdown halts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from ..core.enums import OrderSide, OrderType, SignalType
from ..core.logging_config import get_logger
from ..models import Fill, Order, Signal
from ..portfolio import Portfolio
from ..portfolio.analytics import PerformanceReport
from ..risk import FixedRiskSizer, PositionSizer, RiskManager
from ..strategies.base import Strategy, StrategyContext

logger = get_logger(__name__)


@dataclass
class BacktestResult:
    portfolio: Portfolio
    performance: PerformanceReport
    equity_curve: pd.Series
    orders: list[Order] = field(default_factory=list)
    blocked_orders: int = 0

    def summary(self) -> dict:
        p = self.performance
        return {
            "total_return": round(p.total_return, 4),
            "cagr": round(p.cagr, 4),
            "sharpe": round(p.sharpe, 3),
            "sortino": round(p.sortino, 3),
            "calmar": round(p.calmar, 3),
            "max_drawdown": round(p.max_drawdown, 4),
            "volatility": round(p.volatility, 4),
            "num_trades": p.trades.num_trades,
            "win_rate": round(p.trades.win_rate, 3),
            "profit_factor": round(p.trades.profit_factor, 3),
            "final_equity": round(float(self.equity_curve.iloc[-1]), 2) if len(self.equity_curve) else 0.0,
        }


class BacktestEngine:
    """Vectorised-data, event-loop backtester for a single strategy."""

    def __init__(
        self,
        strategy: Strategy,
        *,
        starting_cash: float = 100_000.0,
        commission_per_share: float = 0.005,
        slippage_bps: float = 1.0,
        sizer: PositionSizer | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self.strategy = strategy
        self.starting_cash = starting_cash
        self.commission_per_share = commission_per_share
        self.slippage_bps = slippage_bps
        self.sizer = sizer or FixedRiskSizer(risk_pct=0.01)
        self.risk = risk_manager or RiskManager()

    def run(self, data: dict[str, pd.DataFrame]) -> BacktestResult:
        """Run the backtest over ``{symbol: ohlcv_dataframe}``."""
        if not data:
            raise ValueError("No data supplied to backtest")

        portfolio = Portfolio(self.starting_cash)
        orders: list[Order] = []
        blocked = 0

        # Unified, sorted timeline across all symbols.
        timeline = sorted(set().union(*[df.index for df in data.values()]))
        self.risk.start_day(self.starting_cash,
                            today=pd.Timestamp(timeline[0]).date())
        current_day = pd.Timestamp(timeline[0]).date()

        for ts in timeline:
            # Roll the risk "day" so max-daily-loss resets each trading session.
            ts_day = pd.Timestamp(ts).date()
            if ts_day != current_day:
                self.risk.start_day(portfolio.equity, today=ts_day)
                current_day = ts_day

            prices: dict[str, float] = {}
            for symbol, df in data.items():
                if ts not in df.index:
                    continue
                window = df.loc[:ts]
                window.attrs["symbol"] = symbol
                prices[symbol] = float(df.loc[ts, "close"])

                if len(window) < self.strategy.warmup:
                    continue

                context = StrategyContext(
                    positions=portfolio.positions,
                    equity=portfolio.equity,
                    cash=portfolio.cash,
                )
                try:
                    signals = self.strategy.generate_signals(window, context)
                except Exception:  # noqa: BLE001 - never let one bar kill the run
                    logger.exception("Strategy error at %s for %s", ts, symbol)
                    signals = []

                for signal in signals:
                    order = self._build_order(signal, portfolio, prices[symbol])
                    if order is None:
                        continue
                    decision = self.risk.check_order(
                        order, prices[symbol], portfolio.equity, portfolio.positions
                    )
                    if not decision:
                        blocked += 1
                        continue
                    fill = self._simulate_fill(order, prices[symbol], ts)
                    if fill is None:
                        continue
                    portfolio.apply_fill(fill, strategy=self.strategy.name)
                    orders.append(order)

            # Mark to market and run the continuous risk monitor.
            equity = portfolio.mark_to_market(prices, when=pd.Timestamp(ts).to_pydatetime())
            self.risk.update_equity(equity)

        equity_curve = portfolio.equity_curve()
        performance = portfolio.performance()
        return BacktestResult(portfolio, performance, equity_curve, orders, blocked)

    # --- helpers --------------------------------------------------------
    def _build_order(self, signal: Signal, portfolio: Portfolio, price: float) -> Order | None:
        symbol = signal.symbol
        if signal.type in {SignalType.CLOSE, SignalType.SELL}:
            pos = portfolio.positions.get(symbol)
            if not pos or abs(pos.quantity) < 1e-9:
                return None
            side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
            return Order(symbol=symbol, side=side, quantity=abs(pos.quantity),
                         order_type=OrderType.MARKET, strategy=self.strategy.name)

        if signal.type in {SignalType.BUY, SignalType.SCALE_IN}:
            qty = self.sizer.size(
                equity=portfolio.equity,
                price=price,
                stop_price=signal.stop_loss,
                volatility=signal.metadata.get("volatility"),
            )
            # Cap by available cash (long-only buying power in backtest).
            max_affordable = portfolio.cash / (price * (1 + self.slippage_bps / 1e4))
            qty = min(qty, int(max_affordable))
            if qty <= 0:
                return None
            return Order(symbol=symbol, side=OrderSide.BUY, quantity=qty,
                         order_type=OrderType.MARKET, strategy=self.strategy.name)
        return None

    def _simulate_fill(self, order: Order, price: float, ts) -> Fill | None:
        slip = price * (self.slippage_bps / 10_000.0)
        fill_price = price + slip if order.side == OrderSide.BUY else price - slip
        commission = order.quantity * self.commission_per_share
        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            timestamp=pd.Timestamp(ts).to_pydatetime(),
        )
