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
        auto_symbols: list[str] | None = None,
        sizer: PositionSizer | None = None,
        risk_manager: RiskManager | None = None,
        notifier: Notifier | None = None,
        store: ApprovalStore | None = None,
        max_capital: float = 0.0,
        pending_ttl: float = 3600.0,
        cooldown: float = 3600.0,
        bars_cache_ttl: float = 600.0,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.data = data_provider
        # Trusted symbols trade automatically; everything else needs SMS approval.
        self.auto_symbols = [s.upper() for s in (auto_symbols or [])]
        self._auto_set = set(self.auto_symbols)
        # Symbols we ask permission for (the universe minus the trusted set).
        self.ask_symbols = [s.upper() for s in universe if s.upper() not in self._auto_set]
        self.universe = self.auto_symbols + self.ask_symbols
        self.sizer = sizer or FixedRiskSizer(0.01)
        self.risk = risk_manager or RiskManager()
        self.notifier = notifier or create_notifier()
        self.store = store or ApprovalStore()
        # Cap how much the bot will deploy regardless of account size (0 = no cap).
        self.max_capital = max_capital
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
        logger.info("ApprovalTradingEngine started: %s | %d auto, %d ask",
                    self.strategy.name, len(self.auto_symbols), len(self.ask_symbols))
        self.notifier.send(
            "QuantTrade",
            f"Bot started: auto-trading {len(self.auto_symbols)} core stocks, and "
            f"texting you for approval on {len(self.ask_symbols)} others.")

    def stop(self) -> None:
        self._running = False

    # --- main loop ------------------------------------------------------
    def run_once(self) -> dict:
        account = self.broker.get_account()
        self.risk.update_equity(account.equity)
        self.store.expire_old(self.pending_ttl)
        self._handle_exits()
        self._execute_approved()
        self._auto_buy_trusted(account.equity)            # core 15: no permission
        if not self.store.has_outstanding():
            self._scan_and_request(account.equity)        # others: ask first
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

    def _cancel_symbol_orders(self, symbol: str) -> None:
        """Cancel any resting orders for a symbol (e.g. its protective stop)."""
        try:
            for o in self.broker.get_open_orders():
                if o.symbol == symbol:
                    self.broker.cancel_order(o.broker_order_id or o.id)
        except Exception:  # noqa: BLE001
            logger.exception("could not cancel orders for %s", symbol)

    def _sell(self, symbol: str, pos, price: float) -> None:
        self._cancel_symbol_orders(symbol)  # avoid an orphaned protective stop
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        order = Order(symbol=symbol, side=side, quantity=abs(pos.quantity),
                      order_type=OrderType.MARKET, strategy=self.strategy.name)
        try:
            self.broker.submit_order(order)
        except Exception:  # noqa: BLE001
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

    # --- safety controls (used by run_bot) ------------------------------
    def flatten_all(self) -> int:
        """Cancel all open orders and sell every position. Returns # sold."""
        try:
            for o in self.broker.get_open_orders():
                self.broker.cancel_order(o.broker_order_id or o.id)
        except Exception:  # noqa: BLE001
            logger.exception("cancel-all failed")
        positions = [p for p in self.broker.get_positions() if abs(p.quantity) > 1e-9]
        for pos in positions:
            price = self._last_price(pos.symbol) or pos.last_price
            self._sell(pos.symbol, pos, price)
        return len(positions)

    def protect_positions(self, stop_pct: float) -> None:
        """Ensure each long position has a protective stop order at the broker."""
        if stop_pct <= 0:
            return
        try:
            protected = {o.symbol for o in self.broker.get_open_orders()}
        except Exception:  # noqa: BLE001
            protected = set()
        for pos in self.broker.get_positions():
            if pos.quantity <= 0 or pos.symbol in protected:
                continue
            stop_price = round(pos.avg_price * (1 - stop_pct), 2)
            order = Order(symbol=pos.symbol, side=OrderSide.SELL, quantity=abs(pos.quantity),
                          order_type=OrderType.STOP, stop_price=stop_price,
                          strategy=self.strategy.name)
            try:
                self.broker.submit_order(order)
                logger.info("Protective stop for %s @ $%.2f", pos.symbol, stop_price)
            except Exception:  # noqa: BLE001
                logger.exception("could not place protective stop for %s", pos.symbol)

    def _last_price(self, symbol: str) -> float:
        try:
            df = self._get_bars(symbol)
            return float(df["close"].iloc[-1]) if df is not None and len(df) else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    def _investable(self, equity: float) -> float:
        """Equity the bot is allowed to size against (capped by max_capital)."""
        return min(equity, self.max_capital) if self.max_capital else equity

    def _deployed(self) -> float:
        """Total dollar value currently invested in positions."""
        return sum(abs(getattr(p, "market_value", 0.0))
                   for p in self.broker.get_positions())

    def _buy(self, symbol: str, price: float, stop: float | None, equity: float,
             positions: dict, *, approved: bool) -> tuple[bool, str]:
        """Size, risk-check and place a buy. Returns (success, reason)."""
        invest = self._investable(equity)
        remaining = None
        # Enforce the capital cap on TOTAL deployed money, not just per position.
        if self.max_capital:
            remaining = self.max_capital - self._deployed()
            if remaining < max(price * 0.0001, 1.0):
                return False, "capital cap reached"
        qty = self.sizer.size(equity=invest, price=price, stop_price=stop)
        if remaining is not None:
            qty = min(qty, remaining / price)  # don't exceed the remaining budget
        if qty <= 0:
            return False, "size 0"
        order = Order(symbol=symbol, side=OrderSide.BUY, quantity=qty,
                      order_type=OrderType.MARKET, strategy=self.strategy.name)
        if not self.risk.check_order(order, price, equity, positions):
            return False, "risk limit"
        try:
            self.broker.submit_order(order)
        except Exception as exc:  # noqa: BLE001
            logger.exception("buy failed for %s", symbol)
            return False, str(exc)
        tag = "you approved" if approved else "core auto-trade"
        self.notifier.send("QuantTrade: bought",
                           f"BUY {qty:g} {symbol} @ ~${price:,.2f} ({tag})")
        return True, "ok"

    def _held_or_pending(self) -> set[str]:
        """Symbols we already own OR have an unfilled order for (don't re-buy)."""
        blocked = {p.symbol for p in self.broker.get_positions()
                   if abs(p.quantity) > 1e-9}
        try:
            blocked |= {o.symbol for o in self.broker.get_open_orders()}
        except Exception:  # noqa: BLE001 - some brokers may not list orders
            logger.exception("could not fetch open orders")
        return blocked

    def _auto_buy_trusted(self, equity: float) -> None:
        """Trade the trusted core stocks automatically -- no approval needed."""
        positions = {p.symbol: p for p in self.broker.get_positions()}
        blocked = self._held_or_pending()
        for symbol in self.auto_symbols:
            if symbol in blocked:
                continue
            try:
                signal, price = self._signal_for(symbol, positions)
            except Exception:  # noqa: BLE001
                logger.exception("auto-buy check failed for %s", symbol)
                continue
            if signal and signal.type in {SignalType.BUY, SignalType.SCALE_IN}:
                ok, reason = self._buy(symbol, price, signal.stop_loss, equity,
                                       positions, approved=False)
                if ok:
                    blocked.add(symbol)  # don't buy it again until it fills

    def _execute_approved(self) -> None:
        positions = {p.symbol: p for p in self.broker.get_positions()}
        equity = self.broker.get_account().equity
        blocked = self._held_or_pending()
        for req in self.store.pop_approved():
            symbol = req["symbol"]
            if symbol in blocked:
                self.store.mark_executed(symbol)
                continue
            ok, reason = self._buy(symbol, float(req.get("price") or 0.0),
                                   req.get("stop_loss"), equity, positions, approved=True)
            if not ok:
                self.notifier.send("QuantTrade", f"Couldn't buy {symbol} ({reason}).")
            self.store.mark_executed(symbol)

    def _scan_and_request(self, equity: float) -> None:
        positions = {p.symbol: p for p in self.broker.get_positions()}
        blocked = self._held_or_pending()
        best = None  # (strength, symbol, price, reason, stop)
        for symbol in self.ask_symbols:
            if symbol in blocked:
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
            f"Reply BUY to buy or SKIP to skip.",
        )
        logger.info("Requested approval to buy %s", symbol)
