"""Interactive Brokers adapter (via ``ib_insync`` + TWS/IB Gateway).

Unlike the REST brokers, IBKR exposes a *socket* API. Orders flow through a
running **Trader Workstation (TWS)** or **IB Gateway** process that proxies to
IB's servers. We use the third-party ``ib_insync`` convenience library on top of
the official ``ibapi``.

Connection
----------
* Host: ``127.0.0.1`` (the gateway runs on the same machine as the bot)
* Port: ``7497`` paper TWS, ``7496`` live TWS, ``4002`` paper Gateway,
        ``4001`` live Gateway
* ``clientId``: an integer that disambiguates concurrent API sessions.

``ib_insync`` mapping notes
---------------------------
* Instruments are :class:`ib_insync.Stock` contracts (qualified via
  ``ib.qualifyContracts``).
* Orders are :class:`ib_insync.MarketOrder` / ``LimitOrder`` / ``StopOrder`` /
  ``StopLimitOrder``; ``ib.placeOrder`` returns a :class:`Trade`.
* ``ib.accountSummary()`` and ``ib.positions()`` feed account/position queries.

Library: https://github.com/erdewit/ib_insync
Install: ``pip install ib_insync``

Note: many calls require a *live* TWS/Gateway socket. Without one, ``connect``
raises :class:`BrokerConnectionError`; the structural mapping is still real so
the adapter works the moment a gateway is reachable.
"""
from __future__ import annotations

from typing import Any

from ..core.enums import OrderSide, OrderStatus, OrderType
from ..core.exceptions import BrokerConnectionError, OrderRejectedError
from ..core.logging_config import get_logger
from ..core.security import SecretVault
from ..models import AccountSnapshot, Order, Position
from .base import Broker

logger = get_logger(__name__)

PAPER_PORT = 7497
LIVE_PORT = 7496

_STATUS_FROM_IB = {
    "PendingSubmit": OrderStatus.PENDING,
    "PendingCancel": OrderStatus.CANCELLED,
    "PreSubmitted": OrderStatus.SUBMITTED,
    "Submitted": OrderStatus.SUBMITTED,
    "ApiCancelled": OrderStatus.CANCELLED,
    "Cancelled": OrderStatus.CANCELLED,
    "Filled": OrderStatus.FILLED,
    "Inactive": OrderStatus.REJECTED,
}


class InteractiveBrokersBroker(Broker):
    """Interactive Brokers adapter backed by ``ib_insync``."""

    name = "interactive_brokers"
    supports_fractional = True
    supports_shorting = True

    def __init__(self, host: str = "127.0.0.1", port: int = PAPER_PORT,
                 client_id: int = 1) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: Any = None
        self._account_id = ""

    # --- internals ------------------------------------------------------
    def _require_ib(self):
        """Lazily import ``ib_insync``; raise a clear install hint if missing."""
        try:
            import ib_insync  # noqa: PLC0415
        except ImportError as exc:
            raise BrokerConnectionError(
                "InteractiveBrokersBroker requires the 'ib_insync' library and a "
                "running TWS / IB Gateway. Install it with: pip install ib_insync"
            ) from exc
        return ib_insync

    def _contract(self, symbol: str):
        ib_insync = self._require_ib()
        contract = ib_insync.Stock(symbol, "SMART", "USD")
        if self._ib is not None:
            self._ib.qualifyContracts(contract)
        return contract

    # --- mapping --------------------------------------------------------
    def _to_broker_order(self, order: Order):
        """Map a platform :class:`Order` to an ``ib_insync`` order object."""
        ib_insync = self._require_ib()
        action = "BUY" if order.side == OrderSide.BUY else "SELL"
        qty = order.quantity
        if order.order_type == OrderType.MARKET:
            return ib_insync.MarketOrder(action, qty)
        if order.order_type == OrderType.LIMIT:
            return ib_insync.LimitOrder(action, qty, order.limit_price)
        if order.order_type == OrderType.STOP:
            return ib_insync.StopOrder(action, qty, order.stop_price)
        if order.order_type == OrderType.STOP_LIMIT:
            return ib_insync.StopLimitOrder(action, qty, order.limit_price, order.stop_price)
        if order.order_type == OrderType.TRAILING_STOP:
            o = ib_insync.Order(orderType="TRAIL", action=action, totalQuantity=qty)
            if order.trail_amount is not None:
                o.auxPrice = order.trail_amount
            return o
        return ib_insync.MarketOrder(action, qty)

    def _from_broker_order(self, trade: Any, order: Order | None = None) -> Order:
        """Map an ``ib_insync`` ``Trade`` back into a platform :class:`Order`."""
        contract = getattr(trade, "contract", None)
        ib_order = getattr(trade, "order", None)
        status = getattr(trade, "orderStatus", None)
        side = OrderSide.BUY
        if ib_order is not None and getattr(ib_order, "action", "BUY") == "SELL":
            side = OrderSide.SELL
        result = order or Order(
            symbol=getattr(contract, "symbol", ""),
            side=side,
            quantity=float(getattr(ib_order, "totalQuantity", 0.0) or 0.0),
        )
        if ib_order is not None:
            result.broker_order_id = str(getattr(ib_order, "orderId", "") or "")
        if status is not None:
            result.status = _STATUS_FROM_IB.get(
                getattr(status, "status", ""), OrderStatus.SUBMITTED
            )
            result.filled_quantity = float(getattr(status, "filled", 0.0) or 0.0)
            result.avg_fill_price = float(getattr(status, "avgFillPrice", 0.0) or 0.0)
        result.account_id = self._account_id
        return result

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        """Open a socket to TWS / IB Gateway at ``host:port``."""
        ib_insync = self._require_ib()
        # account_id is optional for IBKR; credentials live in TWS itself.
        try:
            creds = SecretVault().get_broker_credentials(self.name)
            self._account_id = creds.account_id
        except Exception:  # noqa: BLE001 - IBKR auth is handled by the gateway
            self._account_id = ""
        self._ib = ib_insync.IB()
        try:
            self._ib.connect(self.host, self.port, clientId=self.client_id)
        except Exception as exc:  # ib_insync raises ConnectionError/TimeoutError
            self._ib = None
            raise BrokerConnectionError(
                f"Could not connect to IB Gateway/TWS at {self.host}:{self.port}. "
                "Is TWS or IB Gateway running with API access enabled?"
            ) from exc
        if not self._account_id:
            accounts = self._ib.managedAccounts()
            self._account_id = accounts[0] if accounts else ""
        logger.info("Connected to IBKR at %s:%s account=%s",
                    self.host, self.port, self._account_id)

    def disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:  # pragma: no cover - defensive
                pass
        self._ib = None

    @property
    def is_connected(self) -> bool:
        return self._ib is not None and bool(self._ib.isConnected())

    def _check(self) -> None:
        if not self.is_connected:
            raise BrokerConnectionError("InteractiveBrokersBroker is not connected")

    # --- orders ---------------------------------------------------------
    def submit_order(self, order: Order) -> Order:
        self._check()
        contract = self._contract(order.symbol)
        ib_order = self._to_broker_order(order)
        try:
            trade = self._ib.placeOrder(contract, ib_order)
        except Exception as exc:  # noqa: BLE001
            raise OrderRejectedError(f"IBKR rejected order: {exc}") from exc
        return self._from_broker_order(trade, order)

    def cancel_order(self, order_id: str) -> bool:
        self._check()
        for trade in self._ib.openTrades():
            if str(getattr(trade.order, "orderId", "")) == str(order_id):
                self._ib.cancelOrder(trade.order)
                return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        self._check()
        for trade in self._ib.trades():
            if str(getattr(trade.order, "orderId", "")) == str(order_id):
                return self._from_broker_order(trade)
        return None

    def get_open_orders(self) -> list[Order]:
        self._check()
        return [self._from_broker_order(t) for t in self._ib.openTrades()]

    # --- account / positions -------------------------------------------
    def get_account(self) -> AccountSnapshot:
        self._check()
        values = {v.tag: v.value for v in self._ib.accountSummary()}
        return AccountSnapshot(
            cash=float(values.get("TotalCashValue", 0.0) or 0.0),
            equity=float(values.get("NetLiquidation", 0.0) or 0.0),
            buying_power=float(values.get("BuyingPower", 0.0) or 0.0),
            positions_value=float(values.get("GrossPositionValue", 0.0) or 0.0),
            margin_used=float(values.get("InitMarginReq", 0.0) or 0.0),
            account_id=self._account_id or "default",
        )

    def get_positions(self) -> list[Position]:
        self._check()
        positions: list[Position] = []
        for p in self._ib.positions():
            contract = getattr(p, "contract", None)
            positions.append(Position(
                symbol=getattr(contract, "symbol", ""),
                quantity=float(getattr(p, "position", 0.0) or 0.0),
                avg_price=float(getattr(p, "avgCost", 0.0) or 0.0),
                last_price=0.0,
            ))
        return positions
