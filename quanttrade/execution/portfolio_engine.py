"""Portfolio rebalancing engine for the ensemble allocator.

Unlike the per-symbol engines, this looks at the whole basket each day, asks the
:class:`EnsembleAllocator` for target weights, and rebalances the broker's book
to match (within the capital cap). Rebalances once per trading day; holds between.

Exposes the same surface (broker, risk, notifier, data, strategy, universe,
start/stop/run_once/flatten_all/protect_positions/watchlist_rows) so it drops
into ``run_bot.run_cycle`` like the other engines.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..brokers.base import Broker
from ..core.enums import BarInterval, OrderSide, OrderType
from ..core.logging_config import get_logger
from ..data.base import MarketDataProvider
from ..models import Order
from ..notifications import Notifier, create_notifier
from ..risk import RiskManager
from ..strategies.ensemble import EnsembleAllocator

logger = get_logger(__name__)


class _Named:
    name = "ensemble"


class PortfolioEngine:
    def __init__(self, broker: Broker, data_provider: MarketDataProvider, universe: list[str],
                 *, risk_manager: RiskManager | None = None, notifier: Notifier | None = None,
                 max_capital: float = 0.0, allocator: EnsembleAllocator | None = None,
                 rebalance_band: float = 0.02) -> None:
        self.broker = broker
        self.data = data_provider
        self.universe = [s.strip().upper() for s in universe]
        self.risk = risk_manager or RiskManager()
        self.notifier = notifier or create_notifier()
        self.max_capital = max_capital
        self.allocator = allocator or EnsembleAllocator()
        self.rebalance_band = rebalance_band      # ignore drift smaller than this * capital
        self.strategy = _Named()
        self._bars: tuple[datetime, dict] | None = None
        self._last_rebalance = None

    # --- lifecycle ------------------------------------------------------
    def start(self) -> None:
        if not self.broker.is_connected:
            self.broker.connect()
        self.risk.start_day(self.broker.get_account().equity)
        logger.info("PortfolioEngine (ensemble) started over %d symbols", len(self.universe))
        self.notifier.send("QuantTrade",
                           f"Bot started: ensemble strategy over {len(self.universe)} symbols.")

    def stop(self) -> None:
        pass

    def protect_positions(self, stop_pct: float) -> None:
        # The ensemble manages risk via regime gating + vol-targeted exposure.
        return

    # --- data -----------------------------------------------------------
    def _all_bars(self) -> dict:
        now = datetime.now(timezone.utc)
        if self._bars and (now - self._bars[0]).total_seconds() < 3600:
            return self._bars[1]
        bars = self.data.get_multiple(self.universe, now - timedelta(days=400), now,
                                      BarInterval.DAY_1)
        self._bars = (now, bars)
        return bars

    # --- main -----------------------------------------------------------
    def run_once(self) -> dict:
        account = self.broker.get_account()
        self.risk.update_equity(account.equity)
        today = datetime.now().date()
        if self._last_rebalance == today:
            return {"equity": account.equity, "rebalanced": False}

        bars = self._all_bars()
        rows = self.allocator.detail(bars)
        if not rows:
            return {"equity": account.equity, "rebalanced": False}
        prices = {r["symbol"]: r["last_price"] for r in rows}
        weights = {r["symbol"]: r["weight"] for r in rows}

        capital = min(account.equity, self.max_capital) if self.max_capital else account.equity
        positions = {p.symbol: p for p in self.broker.get_positions()}
        band = max(capital * self.rebalance_band, 1.0)

        # Feed prices to a paper broker so its market orders can fill.
        if hasattr(self.broker, "update_prices"):
            self.broker.update_prices(prices)

        n_trades = 0
        for symbol in self.universe:
            price = prices.get(symbol)
            if not price or price <= 0:
                continue
            target_val = weights.get(symbol, 0.0) * capital
            pos = positions.get(symbol)
            cur_val = (pos.quantity * price) if pos else 0.0
            diff = target_val - cur_val
            if abs(diff) < band:
                continue
            if diff > 0:
                order = Order(symbol=symbol, side=OrderSide.BUY, quantity=diff / price,
                              order_type=OrderType.MARKET, strategy="ensemble")
                if not self.risk.check_order(order, price, account.equity, positions):
                    continue
            else:
                qty = min(pos.quantity if pos else 0.0, abs(diff) / price)
                if qty <= 0:
                    continue
                order = Order(symbol=symbol, side=OrderSide.SELL, quantity=qty,
                              order_type=OrderType.MARKET, strategy="ensemble")
            try:
                self.broker.submit_order(order)
                n_trades += 1
            except Exception:  # noqa: BLE001
                logger.exception("rebalance order failed for %s", symbol)

        self._last_rebalance = today
        if n_trades:
            self.notifier.send("QuantTrade: rebalanced",
                               f"Ensemble rebalanced the portfolio: {n_trades} trades, "
                               f"holding {sum(1 for w in weights.values() if w > 0)} names.")
        logger.info("Ensemble rebalanced: %d trades", n_trades)
        return {"equity": account.equity, "rebalanced": True, "trades": n_trades}

    # --- kill switch ----------------------------------------------------
    def flatten_all(self) -> int:
        try:
            for o in self.broker.get_open_orders():
                self.broker.cancel_order(o.broker_order_id or o.id)
        except Exception:  # noqa: BLE001
            logger.exception("cancel-all failed")
        positions = [p for p in self.broker.get_positions() if abs(p.quantity) > 1e-9]
        for pos in positions:
            try:
                self.broker.submit_order(Order(symbol=pos.symbol, side=OrderSide.SELL,
                                               quantity=abs(pos.quantity),
                                               order_type=OrderType.MARKET, strategy="ensemble"))
            except Exception:  # noqa: BLE001
                logger.exception("flatten sell failed for %s", pos.symbol)
        self._last_rebalance = None
        return len(positions)

    # --- dashboard ------------------------------------------------------
    def watchlist_rows(self) -> list[dict]:
        try:
            rows = self.allocator.detail(self._all_bars())
        except Exception:  # noqa: BLE001
            logger.exception("ensemble watchlist failed")
            return []
        held = {p.symbol for p in self.broker.get_positions() if abs(p.quantity) > 1e-9}
        for r in rows:
            r["held"] = r["symbol"] in held
            r["position_qty"] = 0
        return rows
