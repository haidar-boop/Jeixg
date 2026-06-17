"""Approval-gated trading engine.

Scans a universe of stocks for opportunities and, instead of buying
automatically, **texts the user for permission** before opening any new
position. Exits are handled automatically (to protect profits / cut losses).

Cycle:
    1. expire stale approval requests
    2. auto-sell held positions that hit an exit/stop signal (texts the result)
    3. execute any buys the user approved via SMS (texts confirmation)
    4. if nothing is awaiting a reply, scan the universe for the best new
       opportunity and text the user to ask permission

One request is outstanding at a time, so the user can reply a plain YES / NO.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..brokers.base import Broker
from ..core.enums import BarInterval, OrderSide, OrderType, SignalType
from ..core.logging_config import get_logger
from ..data.base import MarketDataProvider
from ..models import Order
from ..notifications import Notifier, create_notifier
from ..notifications.approvals import ApprovalStore
from ..risk import FixedRiskSizer, PositionSizer, RiskManager
from ..strategies.base import Strategy, StrategyContext

logger = get_logger(__name__)


class ApprovalTradingEngine:
    """Scans for opportunities and trades only with SMS approval for entries."""

    def __init__(
        self,
        strategy: Strategy,
        broker: Broker,
        data_provider: MarketDataProvider,
        universe: list[str],
        *,
        sizer: PositionSizer | None = None,
        risk_manager: RiskManager | None = None,
        notifier: Notifier | None = None,
        store: ApprovalStore | None = None,
        pending_ttl: float = 3600.0,
        cooldown: float = 3600.0,
        bars_cache_ttl: float = 600.0,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.data = data_provider
        self.universe = universe
        self.sizer = sizer or FixedRiskSizer(0.01)
        self.risk = risk_manager or RiskManager()
        self.notifier = notifier or create_notifier()
        self.store = store or ApprovalStore()
        self.pending_ttl = pending_ttl
        self.cooldown = cooldown
        self.bars_cache_ttl = bars_cache_ttl
        self._bars: dict[str, tuple[datetime, object]] = {}
        self._running = False

    # --- lifecycle ------------------------------------------------------
    def start(self) -> None:
        if not self.broker.is_connected:
            self.broker.connect()
        self.risk.start_day(self.broker.get_account().equity)
        self._running = True
        logger.info("ApprovalTradingEngine started: %s over %d symbols",
                    self.strategy.name, len(self.universe))
        self.notifier.send("QuantTrade", f"Bot started (approval mode): scanning "
                                         f"{len(self.universe)} stocks. I'll text before buying.")

    def stop(self) -> None:
        self._running = False

    # --- main loop ------------------------------------------------------
    def run_once(self) -> dict:
        account = self.broker.get_account()
        self.risk.update_equity(account.equity)
        self.store.expire_old(self.pending_ttl)
        self._handle_exits()
        self._execute_approved()
        if not self.store.has_outstanding():
            self._scan_and_request(account.equity)
        return {"equity": account.equity, "outstanding": self.store.has_outstanding()}

    # --- helpers --------------------------------------------------------
    def _get_bars(self, symbol: str):
        now = datetime.now(timezone.utc)
        hit = self._bars.get(symbol)
        if hit and (now - hit[0]).total_seconds() < self.bars_cache_ttl:
            return hit[1]
        df = self.data.get_historical_bars(
            symbol, now - timedelta(days=400), now, BarInterval.DAY_1)
        self._bars[symbol] = (now, df)
        return df

    def _signal_for(self, symbol: str, positions: dict):
        df = self._get_bars(symbol)
        if df is None or len(df) < getattr(self.strategy, "warmup", 50):
            return None, None
        df = df.copy()
        df.attrs["symbol"] = symbol
        ctx = StrategyContext(positions=positions)
        signals = self.strategy.generate_signals(df, ctx)
        price = float(df["close"].iloc[-1])
        return (signals[0] if signals else None), price

    def _handle_exits(self) -> None:
        positions = {p.symbol: p for p in self.broker.get_positions()}
        for symbol, pos in positions.items():
            if abs(pos.quantity) < 1e-9:
                continue
            try:
                signal, price = self._signal_for(symbol, positions)
            except Exception:  # noqa: BLE001
                logger.exception("exit check failed for %s", symbol)
                continue
            if signal and signal.type in {SignalType.CLOSE, SignalType.SELL}:
                self._sell(symbol, pos, price or pos.last_price)

    def _sell(self, symbol: str, pos, price: float) -> None:
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        order = Order(symbol=symbol, side=side, quantity=abs(pos.quantity),
                      order_type=OrderType.MARKET, strategy=self.strategy.name)
        try:
            self.broker.submit_order(order)
        except Exception as exc:  # noqa: BLE001
            logger.exception("sell failed for %s", symbol)
            return
        pnl = (price - pos.avg_price) * pos.quantity
        result = "WON" if pnl >= 0 else "LOST"
        sign = "+" if pnl >= 0 else "-"
        self.notifier.send(
            f"QuantTrade: sold {symbol} ({result})",
            f"Auto-sold {abs(pos.quantity):g} {symbol} @ ${price:,.2f} | "
            f"{result} {sign}${abs(pnl):,.2f}",
        )

    def _execute_approved(self) -> None:
        positions = {p.symbol: p for p in self.broker.get_positions()}
        equity = self.broker.get_account().equity
        for req in self.store.pop_approved():
            symbol = req["symbol"]
            if symbol in positions and abs(positions[symbol].quantity) > 1e-9:
                self.store.mark_executed(symbol)
                continue
            price = float(req.get("price") or 0.0)
            qty = self.sizer.size(equity=equity, price=price,
                                  stop_price=req.get("stop_loss"))
            if qty <= 0:
                self.store.mark_executed(symbol)
                self.notifier.send("QuantTrade", f"Skipped {symbol}: position size came out to 0.")
                continue
            order = Order(symbol=symbol, side=OrderSide.BUY, quantity=qty,
                          order_type=OrderType.MARKET, strategy=self.strategy.name)
            decision = self.risk.check_order(order, price, equity, positions)
            if not decision:
                self.store.mark_executed(symbol)
                self.notifier.send("QuantTrade", f"Skipped {symbol}: blocked by risk limits.")
                continue
            try:
                self.broker.submit_order(order)
                self.notifier.send("QuantTrade: bought",
                                   f"BUY {qty:g} {symbol} @ ~${price:,.2f} (you approved)")
            except Exception as exc:  # noqa: BLE001
                logger.exception("approved buy failed for %s", symbol)
                self.notifier.send("QuantTrade", f"Could not buy {symbol}: {exc}")
            self.store.mark_executed(symbol)

    def _scan_and_request(self, equity: float) -> None:
        positions = {p.symbol: p for p in self.broker.get_positions()}
        best = None  # (strength, symbol, price, reason, stop)
        for symbol in self.universe:
            if symbol in positions and abs(positions[symbol].quantity) > 1e-9:
                continue
            if self.store.in_cooldown(symbol, self.cooldown):
                continue
            try:
                signal, price = self._signal_for(symbol, positions)
            except Exception:  # noqa: BLE001
                logger.exception("scan failed for %s", symbol)
                continue
            if signal and signal.type in {SignalType.BUY, SignalType.SCALE_IN}:
                reason = signal.metadata.get("reason") or "buy signal"
                cand = (signal.strength, symbol, price, reason, signal.stop_loss)
                if best is None or cand[0] > best[0]:
                    best = cand
        if best is None:
            return
        _, symbol, price, reason, stop = best
        self.store.create_request(symbol, price, reason, stop_loss=stop, strength=best[0])
        self.notifier.send(
            "QuantTrade found an opportunity",
            f"I found {symbol} @ ${price:,.2f} ({reason}). "
            f"Reply YES to buy or NO to skip.",
        )
        logger.info("Requested approval to buy %s", symbol)
