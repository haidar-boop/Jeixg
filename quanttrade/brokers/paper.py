"""Paper-trading broker (simulated execution).

A full in-memory broker used for paper trading, forward testing and as the fill
engine behind the backtester. It models:

* cash / equity / buying-power accounting
* commission (per-share) and slippage (basis points)
* market, limit, stop and stop-limit order types
* long and short positions with correct P&L via :meth:`Position.apply_fill`

Prices are injected by the caller (backtest loop or a live quote feed) through
:meth:`update_price`, keeping the broker deterministic and side-effect free.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..core.enums import OrderSide, OrderStatus, OrderType
from ..core.exceptions import InsufficientFundsError
from ..core.logging_config import get_logger
from ..models import AccountSnapshot, Fill, Order, Position
from .base import Broker

logger = get_logger(__name__)


class PaperBroker(Broker):
    """Deterministic simulated broker."""

    name = "paper"
    supports_fractional = True
    supports_shorting = True

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        commission_per_share: float = 0.005,
        slippage_bps: float = 1.0,
        allow_short: bool = True,
    ) -> None:
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.commission_per_share = commission_per_share
        self.slippage_bps = slippage_bps
        self.allow_short = allow_short
        self._connected = False
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._prices: dict[str, float] = {}
        self._clock: datetime = datetime.now(timezone.utc)

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        self._connected = True
        logger.info("PaperBroker connected (cash=%.2f)", self.cash)

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # --- price feed -----------------------------------------------------
    def update_price(self, symbol: str, price: float, when: datetime | None = None) -> None:
        """Set the current market price for a symbol and process resting orders."""
        self._prices[symbol] = price
        if symbol in self._positions:
            self._positions[symbol].last_price = price
        if when is not None:
            self._clock = when
        self._process_resting_orders(symbol)

    def update_prices(self, prices: dict[str, float], when: datetime | None = None) -> None:
        for sym, px in prices.items():
            self.update_price(sym, px, when)

    def _last_price(self, symbol: str) -> float:
        if symbol not in self._prices:
            raise InsufficientFundsError(f"No price available for {symbol}")
        return self._prices[symbol]

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        adj = price * (self.slippage_bps / 10_000.0)
        return price + adj if side == OrderSide.BUY else price - adj

    # --- order management ----------------------------------------------
    def submit_order(self, order: Order) -> Order:
        order.status = OrderStatus.SUBMITTED
        order.broker_order_id = f"paper-{order.id}"
        order.updated_at = self._clock
        self._orders[order.id] = order
        logger.debug("Submitted %s %s %.4f %s", order.side, order.symbol,
                     order.quantity, order.order_type)

        if order.order_type == OrderType.MARKET:
            self._try_fill(order, self._last_price(order.symbol))
        else:
            # Resting orders are matched against incoming prices.
            if order.symbol in self._prices:
                self._process_resting_orders(order.symbol)
        return order

    def _process_resting_orders(self, symbol: str) -> None:
        price = self._prices.get(symbol)
        if price is None:
            return
        for order in list(self._orders.values()):
            if order.symbol != symbol or not order.is_active:
                continue
            if order.order_type == OrderType.LIMIT:
                if (order.side == OrderSide.BUY and price <= order.limit_price) or (
                    order.side == OrderSide.SELL and price >= order.limit_price
                ):
                    self._try_fill(order, min(price, order.limit_price)
                                   if order.side == OrderSide.BUY
                                   else max(price, order.limit_price))
            elif order.order_type == OrderType.STOP:
                if (order.side == OrderSide.BUY and price >= order.stop_price) or (
                    order.side == OrderSide.SELL and price <= order.stop_price
                ):
                    self._try_fill(order, price)
            elif order.order_type == OrderType.STOP_LIMIT:
                triggered = (
                    order.side == OrderSide.BUY and price >= order.stop_price
                ) or (order.side == OrderSide.SELL and price <= order.stop_price)
                if triggered and (
                    (order.side == OrderSide.BUY and price <= order.limit_price)
                    or (order.side == OrderSide.SELL and price >= order.limit_price)
                ):
                    self._try_fill(order, order.limit_price)

    def _try_fill(self, order: Order, ref_price: float) -> None:
        fill_price = self._apply_slippage(ref_price, order.side)
        qty = order.remaining
        commission = qty * self.commission_per_share
        notional = qty * fill_price

        if order.side == OrderSide.BUY:
            cost = notional + commission
            if cost > self.cash + 1e-6:
                order.status = OrderStatus.REJECTED
                logger.warning("Order %s rejected: insufficient funds (need %.2f, have %.2f)",
                               order.id, cost, self.cash)
                return
            self.cash -= cost
        else:  # SELL
            pos = self._positions.get(order.symbol)
            held = pos.quantity if pos else 0.0
            if not self.allow_short and qty > held + 1e-9:
                order.status = OrderStatus.REJECTED
                logger.warning("Order %s rejected: shorting disabled", order.id)
                return
            self.cash += notional - commission

        pos = self._positions.setdefault(order.symbol, Position(symbol=order.symbol))
        pos.apply_fill(order.side, qty, fill_price, commission)
        pos.last_price = fill_price

        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.commission += commission
        order.status = OrderStatus.FILLED
        order.updated_at = self._clock
        self._fills.append(
            Fill(order_id=order.id, symbol=order.symbol, side=order.side,
                 quantity=qty, price=fill_price, commission=commission, timestamp=self._clock)
        )
        logger.info("FILL %s %s %.4f @ %.4f (comm %.2f)", order.side, order.symbol,
                    qty, fill_price, commission)

        if abs(pos.quantity) < 1e-9:
            # Position closed -> realize and drop it from the book.
            self._positions.pop(order.symbol, None)

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.is_active:
            order.status = OrderStatus.CANCELLED
            order.updated_at = self._clock
            return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_open_orders(self) -> list[Order]:
        return [o for o in self._orders.values() if o.is_active]

    def get_fills(self) -> list[Fill]:
        return list(self._fills)

    # --- account / positions -------------------------------------------
    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    @property
    def positions_value(self) -> float:
        return sum(p.market_value for p in self._positions.values())

    @property
    def equity(self) -> float:
        return self.cash + self.positions_value

    def get_account(self) -> AccountSnapshot:
        pv = self.positions_value
        equity = self.cash + pv
        # Simple Reg-T style buying power for the long-only case.
        buying_power = max(self.cash, 0.0) * 2.0
        return AccountSnapshot(
            cash=self.cash,
            equity=equity,
            buying_power=buying_power,
            positions_value=pv,
            timestamp=self._clock,
        )
