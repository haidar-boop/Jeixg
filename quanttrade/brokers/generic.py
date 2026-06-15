"""Generic REST broker framework.

A configurable adapter that implements the :class:`Broker` interface against any
broker exposing a conventional REST API. Point it at a ``base_url``, describe the
auth scheme and an endpoint map, and it becomes a working broker -- the intended
starting point for integrating a venue that lacks a dedicated adapter.

This is intentionally a template: the request/response *mapping* is where each
real broker differs, so :meth:`_map_order_payload` / :meth:`_parse_*` are the
hooks a subclass overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.exceptions import BrokerConnectionError, OrderRejectedError
from ..core.logging_config import get_logger
from ..models import AccountSnapshot, Order, Position
from .base import Broker

logger = get_logger(__name__)


@dataclass
class RESTConfig:
    base_url: str
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"  # produces "Authorization: Bearer <key>"
    endpoints: dict[str, str] = field(default_factory=lambda: {
        "account": "/account",
        "orders": "/orders",
        "positions": "/positions",
    })
    timeout: float = 10.0


class GenericRESTBroker(Broker):
    """Template broker driven by a :class:`RESTConfig`."""

    name = "generic"

    def __init__(self, config: RESTConfig, api_key: str = "") -> None:
        self.config = config
        self.api_key = api_key
        self._connected = False
        self._session = None

    def _require_requests(self):
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - optional
            raise BrokerConnectionError("Install `requests` to use GenericRESTBroker") from exc
        return requests

    def _headers(self) -> dict[str, str]:
        value = f"{self.config.auth_scheme} {self.api_key}".strip()
        return {self.config.auth_header: value, "Content-Type": "application/json"}

    def _url(self, key: str) -> str:
        return self.config.base_url.rstrip("/") + self.config.endpoints[key]

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        requests = self._require_requests()
        self._session = requests.Session()
        try:
            resp = self._session.get(self._url("account"), headers=self._headers(),
                                     timeout=self.config.timeout)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise BrokerConnectionError(f"Generic broker connect failed: {exc}") from exc
        self._connected = True

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # --- mapping hooks (override per venue) -----------------------------
    def _map_order_payload(self, order: Order) -> dict:
        return {
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": order.quantity,
            "type": order.order_type.value,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
            "time_in_force": order.time_in_force.value,
        }

    def _parse_account(self, data: dict) -> AccountSnapshot:
        return AccountSnapshot(
            cash=float(data.get("cash", 0.0)),
            equity=float(data.get("equity", 0.0)),
            buying_power=float(data.get("buying_power", 0.0)),
        )

    def _parse_position(self, data: dict) -> Position:
        return Position(
            symbol=data["symbol"],
            quantity=float(data.get("qty", 0.0)),
            avg_price=float(data.get("avg_price", 0.0)),
            last_price=float(data.get("last_price", data.get("avg_price", 0.0))),
        )

    # --- order management ----------------------------------------------
    def submit_order(self, order: Order) -> Order:
        resp = self._session.post(self._url("orders"), json=self._map_order_payload(order),
                                  headers=self._headers(), timeout=self.config.timeout)
        if resp.status_code >= 400:
            raise OrderRejectedError(f"Order rejected ({resp.status_code}): {resp.text}")
        body = resp.json()
        order.broker_order_id = str(body.get("id", ""))
        return order

    def cancel_order(self, order_id: str) -> bool:
        url = f"{self._url('orders')}/{order_id}"
        resp = self._session.delete(url, headers=self._headers(), timeout=self.config.timeout)
        return resp.status_code < 400

    def get_order(self, order_id: str) -> Order | None:  # pragma: no cover - venue-specific
        url = f"{self._url('orders')}/{order_id}"
        resp = self._session.get(url, headers=self._headers(), timeout=self.config.timeout)
        return None if resp.status_code >= 400 else None  # override to parse body

    def get_open_orders(self) -> list[Order]:
        resp = self._session.get(self._url("orders"), headers=self._headers(),
                                 timeout=self.config.timeout)
        return [] if resp.status_code >= 400 else []  # override to parse body

    def get_account(self) -> AccountSnapshot:
        resp = self._session.get(self._url("account"), headers=self._headers(),
                                 timeout=self.config.timeout)
        resp.raise_for_status()
        return self._parse_account(resp.json())

    def get_positions(self) -> list[Position]:
        resp = self._session.get(self._url("positions"), headers=self._headers(),
                                 timeout=self.config.timeout)
        if resp.status_code >= 400:
            return []
        return [self._parse_position(p) for p in resp.json()]
