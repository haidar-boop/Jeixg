"""Alpaca broker adapter (REST).

Talks to the Alpaca Trading API over plain HTTPS using ``requests`` so the
platform has no hard dependency on ``alpaca-py``/``alpaca-trade-api``.

API reference
-------------
* Base URL (paper): ``https://paper-api.alpaca.markets``
* Base URL (live):  ``https://api.alpaca.markets``
* Auth headers:     ``APCA-API-KEY-ID`` / ``APCA-API-SECRET-KEY``
* Account:          ``GET /v2/account``
* Submit order:     ``POST /v2/orders``
* Cancel order:     ``DELETE /v2/orders/{id}``
* Get order:        ``GET /v2/orders/{id}``
* Open orders:      ``GET /v2/orders?status=open``
* Positions:        ``GET /v2/positions``

Docs: https://docs.alpaca.markets/reference/

Credentials are resolved from ``SecretVault().get_broker_credentials("alpaca")``
which reads ``QT_ALPACA_API_KEY`` / ``QT_ALPACA_API_SECRET`` from the env.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..core.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from ..core.exceptions import BrokerConnectionError, OrderRejectedError
from ..core.logging_config import get_logger
from ..core.security import SecretVault
from ..models import AccountSnapshot, Order, Position
from .base import Broker

logger = get_logger(__name__)

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"

# platform OrderType -> Alpaca "type"
_TYPE_TO_ALPACA = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP: "stop",
    OrderType.STOP_LIMIT: "stop_limit",
    OrderType.TRAILING_STOP: "trailing_stop",
}
_TYPE_FROM_ALPACA = {v: k for k, v in _TYPE_TO_ALPACA.items()}

# Alpaca order "status" -> platform OrderStatus
_STATUS_FROM_ALPACA = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.PENDING,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "done_for_day": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,
    "pending_cancel": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.CANCELLED,
    "pending_replace": OrderStatus.SUBMITTED,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.PENDING,
    "calculated": OrderStatus.PENDING,
    "stopped": OrderStatus.PENDING,
}

_TIF_TO_ALPACA = {
    TimeInForce.DAY: "day",
    TimeInForce.GTC: "gtc",
    TimeInForce.IOC: "ioc",
    TimeInForce.FOK: "fok",
}


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover - defensive
        return datetime.now(timezone.utc)


class AlpacaBroker(Broker):
    """Alpaca REST broker adapter."""

    name = "alpaca"
    supports_fractional = True
    supports_shorting = True

    def __init__(self, paper: bool = True, base_url: str | None = None) -> None:
        self.paper = paper
        self.base_url = base_url or (PAPER_BASE_URL if paper else LIVE_BASE_URL)
        self._session: Any = None
        self._connected = False
        self._account_id = ""

    # --- internals ------------------------------------------------------
    def _require_requests(self):
        """Lazily import ``requests``; raise a clear install hint if missing."""
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - requests is a core dep
            raise BrokerConnectionError(
                "The 'requests' package is required for AlpacaBroker. "
                "Install it with: pip install requests"
            ) from exc
        return requests

    def _build_session(self):
        requests = self._require_requests()
        creds = SecretVault().get_broker_credentials(self.name)
        self._account_id = creds.account_id
        session = requests.Session()
        session.headers.update({
            "APCA-API-KEY-ID": creds.api_key,
            "APCA-API-SECRET-KEY": creds.api_secret,
            "Content-Type": "application/json",
        })
        return session

    def _request(self, method: str, path: str, **kwargs) -> Any:
        if self._session is None:
            raise BrokerConnectionError("AlpacaBroker is not connected; call connect()")
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, timeout=30, **kwargs)
        if resp.status_code == 401:
            raise BrokerConnectionError("Alpaca authentication failed (401)")
        if resp.status_code >= 400:
            raise OrderRejectedError(
                f"Alpaca API error {resp.status_code}: {resp.text}"
            )
        if resp.text:
            return resp.json()
        return None

    # --- mapping --------------------------------------------------------
    def _to_broker_order(self, order: Order) -> dict[str, Any]:
        """Map a platform :class:`Order` to an Alpaca ``POST /v2/orders`` body."""
        body: dict[str, Any] = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": "buy" if order.side == OrderSide.BUY else "sell",
            "type": _TYPE_TO_ALPACA.get(order.order_type, "market"),
            "time_in_force": _TIF_TO_ALPACA.get(order.time_in_force, "day"),
        }
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            body["limit_price"] = str(order.limit_price)
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            body["stop_price"] = str(order.stop_price)
        if order.order_type == OrderType.TRAILING_STOP and order.trail_amount is not None:
            body["trail_price"] = str(order.trail_amount)
        if order.id:
            body["client_order_id"] = order.id
        return body

    def _from_broker_order(self, data: dict[str, Any], order: Order | None = None) -> Order:
        """Map an Alpaca order payload back into a platform :class:`Order`."""
        side = OrderSide.BUY if data.get("side") == "buy" else OrderSide.SELL
        filled_qty = float(data.get("filled_qty") or 0.0)
        avg_price = float(data.get("filled_avg_price") or 0.0)
        result = order or Order(
            symbol=data.get("symbol", ""),
            side=side,
            quantity=float(data.get("qty") or 0.0),
            order_type=_TYPE_FROM_ALPACA.get(data.get("type", "market"), OrderType.MARKET),
        )
        result.broker_order_id = data.get("id", "")
        result.status = _STATUS_FROM_ALPACA.get(data.get("status", ""), OrderStatus.SUBMITTED)
        result.filled_quantity = filled_qty
        result.avg_fill_price = avg_price
        result.updated_at = _parse_ts(data.get("updated_at"))
        result.account_id = self._account_id
        return result

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        """Authenticate by hitting ``GET /v2/account``."""
        self._session = self._build_session()
        try:
            acct = self._request("GET", "/v2/account")
        except Exception:
            self._session = None
            raise
        if not self._account_id:
            self._account_id = acct.get("account_number", "") if acct else ""
        self._connected = True
        logger.info("Connected to Alpaca (%s)", self.base_url)

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
        data = self._request("POST", "/v2/orders", json=self._to_broker_order(order))
        return self._from_broker_order(data, order)

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._request("DELETE", f"/v2/orders/{order_id}")
            return True
        except OrderRejectedError:
            return False

    def get_order(self, order_id: str) -> Order | None:
        try:
            data = self._request("GET", f"/v2/orders/{order_id}")
        except OrderRejectedError:
            return None
        return self._from_broker_order(data) if data else None

    def get_open_orders(self) -> list[Order]:
        data = self._request("GET", "/v2/orders", params={"status": "open"})
        return [self._from_broker_order(o) for o in (data or [])]

    # --- account / positions -------------------------------------------
    def get_account(self) -> AccountSnapshot:
        data = self._request("GET", "/v2/account") or {}
        return AccountSnapshot(
            cash=float(data.get("cash") or 0.0),
            equity=float(data.get("equity") or 0.0),
            buying_power=float(data.get("buying_power") or 0.0),
            positions_value=float(data.get("long_market_value") or 0.0),
            margin_used=float(data.get("initial_margin") or 0.0),
            account_id=data.get("account_number", self._account_id),
        )

    def get_positions(self) -> list[Position]:
        data = self._request("GET", "/v2/positions") or []
        positions: list[Position] = []
        for p in data:
            positions.append(Position(
                symbol=p.get("symbol", ""),
                quantity=float(p.get("qty") or 0.0),
                avg_price=float(p.get("avg_entry_price") or 0.0),
                last_price=float(p.get("current_price") or 0.0),
                realized_pnl=0.0,
            ))
        return positions

    # --- live dashboard extras -----------------------------------------
    def get_account_raw(self) -> dict[str, Any]:
        """Raw Alpaca account payload (includes ``last_equity`` for day P&L)."""
        return self._request("GET", "/v2/account") or {}

    def get_recent_orders(self, limit: int = 50) -> list[Order]:
        """Most recent orders of any status (newest first)."""
        data = self._request("GET", "/v2/orders", params={
            "status": "all", "limit": limit, "direction": "desc",
        })
        return [self._from_broker_order(o) for o in (data or [])]

    def get_portfolio_history(self, period: str = "1M",
                              timeframe: str = "1D") -> list[dict[str, Any]]:
        """Account equity time-series for the dashboard chart."""
        data = self._request("GET", "/v2/account/portfolio/history", params={
            "period": period, "timeframe": timeframe,
        }) or {}
        stamps = data.get("timestamp") or []
        equity = data.get("equity") or []
        out: list[dict[str, Any]] = []
        for ts, eq in zip(stamps, equity):
            if eq is None:
                continue
            out.append({
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                "equity": float(eq),
            })
        return out

    def get_clock(self) -> dict[str, Any]:
        """Market clock: is it open, and the next open/close times."""
        return self._request("GET", "/v2/clock") or {}
