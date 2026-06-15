"""Tradier broker adapter (REST).

Uses the Tradier Brokerage API over HTTPS via ``requests``.

API reference
-------------
* Base URL (sandbox): ``https://sandbox.tradier.com/v1``
* Base URL (live):    ``https://api.tradier.com/v1``
* Auth header:        ``Authorization: Bearer <access_token>``
* Accept header:      ``Accept: application/json``
* Profile:            ``GET /v1/user/profile``        (resolve account id)
* Balances:           ``GET /v1/accounts/{id}/balances``
* Positions:          ``GET /v1/accounts/{id}/positions``
* Place order:        ``POST /v1/accounts/{id}/orders``   (form-encoded)
* Cancel order:       ``DELETE /v1/accounts/{id}/orders/{order_id}``
* Get order:          ``GET /v1/accounts/{id}/orders/{order_id}``
* Open orders:        ``GET /v1/accounts/{id}/orders``

Docs: https://documentation.tradier.com/brokerage-api

Credentials come from ``SecretVault().get_broker_credentials("tradier")`` where
``api_key`` is the OAuth access token and ``account_id`` the account number.
"""
from __future__ import annotations

from typing import Any

from ..core.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from ..core.exceptions import BrokerConnectionError, OrderRejectedError
from ..core.logging_config import get_logger
from ..core.security import SecretVault
from ..models import AccountSnapshot, Order, Position
from .base import Broker

logger = get_logger(__name__)

SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1"
LIVE_BASE_URL = "https://api.tradier.com/v1"

_TYPE_TO_TRADIER = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP: "stop",
    OrderType.STOP_LIMIT: "stop_limit",
}
_TYPE_FROM_TRADIER = {v: k for k, v in _TYPE_TO_TRADIER.items()}

_TIF_TO_TRADIER = {
    TimeInForce.DAY: "day",
    TimeInForce.GTC: "gtc",
    TimeInForce.IOC: "day",  # Tradier equities support day/gtc/pre/post
    TimeInForce.FOK: "day",
}

_STATUS_FROM_TRADIER = {
    "open": OrderStatus.SUBMITTED,
    "pending": OrderStatus.PENDING,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
    "calculated": OrderStatus.PENDING,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "error": OrderStatus.REJECTED,
}


class TradierBroker(Broker):
    """Tradier REST broker adapter."""

    name = "tradier"
    supports_fractional = False
    supports_shorting = True

    def __init__(self, sandbox: bool = True, base_url: str | None = None) -> None:
        self.sandbox = sandbox
        self.base_url = base_url or (SANDBOX_BASE_URL if sandbox else LIVE_BASE_URL)
        self._session: Any = None
        self._connected = False
        self._account_id = ""

    # --- internals ------------------------------------------------------
    def _require_requests(self):
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise BrokerConnectionError(
                "The 'requests' package is required for TradierBroker. "
                "Install it with: pip install requests"
            ) from exc
        return requests

    def _build_session(self):
        requests = self._require_requests()
        creds = SecretVault().get_broker_credentials(self.name)
        self._account_id = creds.account_id
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {creds.api_key}",
            "Accept": "application/json",
        })
        return session

    def _request(self, method: str, path: str, **kwargs) -> Any:
        if self._session is None:
            raise BrokerConnectionError("TradierBroker is not connected; call connect()")
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code == 401:
            raise BrokerConnectionError("Tradier authentication failed (401)")
        if resp.status_code >= 400:
            raise OrderRejectedError(f"Tradier API error {resp.status_code}: {resp.text}")
        return resp.json() if resp.text else None

    def _resolve_account_id(self) -> str:
        if self._account_id:
            return self._account_id
        profile = self._request("GET", "/user/profile") or {}
        accounts = ((profile.get("profile") or {}).get("account")) or {}
        if isinstance(accounts, list):
            accounts = accounts[0] if accounts else {}
        self._account_id = accounts.get("account_number", "")
        return self._account_id

    # --- mapping --------------------------------------------------------
    def _to_broker_order(self, order: Order) -> dict[str, Any]:
        """Map a platform :class:`Order` to Tradier order form fields."""
        body: dict[str, Any] = {
            "class": "equity",
            "symbol": order.symbol,
            "side": "buy" if order.side == OrderSide.BUY else "sell",
            "quantity": str(int(order.quantity)),
            "type": _TYPE_TO_TRADIER.get(order.order_type, "market"),
            "duration": _TIF_TO_TRADIER.get(order.time_in_force, "day"),
        }
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            body["price"] = str(order.limit_price)
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            body["stop"] = str(order.stop_price)
        return body

    def _from_broker_order(self, data: dict[str, Any], order: Order | None = None) -> Order:
        """Map a Tradier order payload back into a platform :class:`Order`."""
        side_raw = (data.get("side") or "buy").lower()
        side = OrderSide.BUY if side_raw.startswith("buy") else OrderSide.SELL
        result = order or Order(
            symbol=data.get("symbol", ""),
            side=side,
            quantity=float(data.get("quantity") or 0.0),
            order_type=_TYPE_FROM_TRADIER.get(data.get("type", "market"), OrderType.MARKET),
        )
        result.broker_order_id = str(data.get("id", ""))
        result.status = _STATUS_FROM_TRADIER.get(
            (data.get("status") or "").lower(), OrderStatus.SUBMITTED
        )
        result.filled_quantity = float(data.get("exec_quantity") or 0.0)
        result.avg_fill_price = float(data.get("avg_fill_price") or 0.0)
        result.account_id = self._account_id
        return result

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        """Authenticate and resolve the account id via ``GET /user/profile``."""
        self._session = self._build_session()
        try:
            self._resolve_account_id()
        except Exception:
            self._session = None
            raise
        self._connected = True
        logger.info("Connected to Tradier (%s) account=%s", self.base_url, self._account_id)

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.close()
        self._session = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # --- orders ---------------------------------------------------------
    def submit_order(self, order: Order) -> Order:
        acct = self._resolve_account_id()
        resp = self._request(
            "POST", f"/accounts/{acct}/orders", data=self._to_broker_order(order)
        ) or {}
        body = resp.get("order", resp)
        if body.get("status") == "error" or "errors" in resp:
            raise OrderRejectedError(f"Tradier rejected order: {resp}")
        return self._from_broker_order(body, order)

    def cancel_order(self, order_id: str) -> bool:
        acct = self._resolve_account_id()
        try:
            resp = self._request("DELETE", f"/accounts/{acct}/orders/{order_id}") or {}
        except OrderRejectedError:
            return False
        return (resp.get("order", {}) or {}).get("status") == "ok"

    def get_order(self, order_id: str) -> Order | None:
        acct = self._resolve_account_id()
        try:
            resp = self._request("GET", f"/accounts/{acct}/orders/{order_id}") or {}
        except OrderRejectedError:
            return None
        body = resp.get("order")
        return self._from_broker_order(body) if body else None

    def get_open_orders(self) -> list[Order]:
        acct = self._resolve_account_id()
        resp = self._request("GET", f"/accounts/{acct}/orders") or {}
        orders = (resp.get("orders") or {}).get("order")
        if orders is None:
            return []
        if isinstance(orders, dict):
            orders = [orders]
        out = [self._from_broker_order(o) for o in orders]
        return [o for o in out if o.is_active]

    # --- account / positions -------------------------------------------
    def get_account(self) -> AccountSnapshot:
        acct = self._resolve_account_id()
        resp = self._request("GET", f"/accounts/{acct}/balances") or {}
        bal = resp.get("balances", {}) or {}
        return AccountSnapshot(
            cash=float((bal.get("cash") or {}).get("cash_available", bal.get("total_cash", 0.0)) or 0.0),
            equity=float(bal.get("total_equity") or 0.0),
            buying_power=float((bal.get("margin") or {}).get("stock_buying_power", 0.0) or 0.0),
            positions_value=float(bal.get("market_value") or 0.0),
            account_id=acct,
        )

    def get_positions(self) -> list[Position]:
        acct = self._resolve_account_id()
        resp = self._request("GET", f"/accounts/{acct}/positions") or {}
        raw = (resp.get("positions") or {})
        if raw in ("null", None):
            return []
        items = raw.get("position") if isinstance(raw, dict) else None
        if items is None:
            return []
        if isinstance(items, dict):
            items = [items]
        positions: list[Position] = []
        for p in items:
            qty = float(p.get("quantity") or 0.0)
            cost = float(p.get("cost_basis") or 0.0)
            positions.append(Position(
                symbol=p.get("symbol", ""),
                quantity=qty,
                avg_price=(cost / qty) if qty else 0.0,
                last_price=0.0,
            ))
        return positions
