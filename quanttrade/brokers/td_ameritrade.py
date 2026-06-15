"""TD Ameritrade broker adapter (REST scaffold).

.. note::
    **TD Ameritrade's developer API has been DEPRECATED and migrated into
    Charles Schwab.** Following Schwab's acquisition of TD Ameritrade, the
    legacy ``api.tdameritrade.com`` endpoints and the developer portal at
    ``developer.tdameritrade.com`` were retired. New API access is provisioned
    through the **Schwab Trader API** at ``https://api.schwabapi.com`` using
    OAuth2 (authorization-code flow) with app key / app secret credentials.

    This module is a thin ``requests``-based *scaffold* that documents the
    historical TDA endpoints and the equivalent Schwab Trader API endpoints.
    The mapping layer is real, but the live network calls raise
    :class:`NotImplementedError` with guidance, because:

    1. Schwab requires a full OAuth2 callback/refresh-token dance that cannot
       be completed headlessly here.
    2. The exact request/response schema differs between the retired TDA API
       and the current Schwab API and should be confirmed against live docs.

API reference (current -- Schwab Trader API)
--------------------------------------------
* Base URL:        ``https://api.schwabapi.com/trader/v1``
* Auth:            ``Authorization: Bearer <access_token>`` (OAuth2)
* Accounts:        ``GET /accounts``  /  ``GET /accounts/{accountNumber}``
* Place order:     ``POST /accounts/{accountNumber}/orders``
* Cancel order:    ``DELETE /accounts/{accountNumber}/orders/{orderId}``
* Get order:       ``GET /accounts/{accountNumber}/orders/{orderId}``
* Open orders:     ``GET /accounts/{accountNumber}/orders?status=WORKING``
* Positions:       ``GET /accounts/{accountNumber}?fields=positions``

API reference (legacy -- retired TD Ameritrade API)
---------------------------------------------------
* Base URL:        ``https://api.tdameritrade.com/v1``
* Accounts:        ``GET /accounts/{accountId}``
* Place order:     ``POST /accounts/{accountId}/orders``
* Positions:       ``GET /accounts/{accountId}?fields=positions``

Docs: https://developer.schwab.com/products/trader-api--individual

Credentials come from ``SecretVault().get_broker_credentials("td_ameritrade")``
where ``api_key`` is the Schwab app key, ``api_secret`` the app secret and
``account_id`` the (hashed) account number.
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

SCHWAB_BASE_URL = "https://api.schwabapi.com/trader/v1"
LEGACY_TDA_BASE_URL = "https://api.tdameritrade.com/v1"

# platform OrderType -> Schwab/TDA order "orderType"
_TYPE_TO_TDA = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP: "STOP",
    OrderType.STOP_LIMIT: "STOP_LIMIT",
    OrderType.TRAILING_STOP: "TRAILING_STOP",
}
_TYPE_FROM_TDA = {v: k for k, v in _TYPE_TO_TDA.items()}

# platform TimeInForce -> Schwab/TDA "duration"
_TIF_TO_TDA = {
    TimeInForce.DAY: "DAY",
    TimeInForce.GTC: "GOOD_TILL_CANCEL",
    TimeInForce.IOC: "FILL_OR_KILL",
    TimeInForce.FOK: "FILL_OR_KILL",
}

# Schwab/TDA order status -> platform OrderStatus
_STATUS_FROM_TDA = {
    "AWAITING_PARENT_ORDER": OrderStatus.PENDING,
    "AWAITING_CONDITION": OrderStatus.PENDING,
    "PENDING_ACTIVATION": OrderStatus.PENDING,
    "QUEUED": OrderStatus.SUBMITTED,
    "WORKING": OrderStatus.SUBMITTED,
    "ACCEPTED": OrderStatus.SUBMITTED,
    "PENDING_CANCEL": OrderStatus.CANCELLED,
    "CANCELED": OrderStatus.CANCELLED,
    "PENDING_REPLACE": OrderStatus.SUBMITTED,
    "REPLACED": OrderStatus.CANCELLED,
    "FILLED": OrderStatus.FILLED,
    "EXPIRED": OrderStatus.EXPIRED,
    "REJECTED": OrderStatus.REJECTED,
}

_MIGRATION_HINT = (
    "TD Ameritrade's API was deprecated and migrated to the Charles Schwab "
    "Trader API (https://api.schwabapi.com). Live trading requires an OAuth2 "
    "access token obtained via Schwab's authorization-code flow. Provision an "
    "app at https://developer.schwab.com, then wire its access/refresh tokens "
    "into this adapter (or use the official 'schwab-py' library)."
)


class TDAmeritradeBroker(Broker):
    """TD Ameritrade / Schwab Trader API adapter (scaffold).

    The mapping helpers are production-shaped, but network methods deliberately
    raise :class:`NotImplementedError` so callers receive clear migration
    guidance rather than silently hitting a retired endpoint.
    """

    name = "td_ameritrade"
    supports_fractional = False
    supports_shorting = True

    def __init__(self, base_url: str | None = None,
                 access_token: str | None = None) -> None:
        self.base_url = base_url or SCHWAB_BASE_URL
        self._access_token = access_token
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
                "The 'requests' package is required for TDAmeritradeBroker. "
                "Install it with: pip install requests"
            ) from exc
        return requests

    def _build_session(self):
        requests = self._require_requests()
        creds = SecretVault().get_broker_credentials(self.name)
        self._account_id = creds.account_id
        token = self._access_token or creds.extra and creds.extra.get("access_token")
        if not token:
            # The vault only holds app key/secret; the OAuth access token must
            # be supplied explicitly or minted via the OAuth flow.
            raise BrokerConnectionError(
                "No OAuth access token available for Schwab/TDA. " + _MIGRATION_HINT
            )
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        return session

    # --- mapping --------------------------------------------------------
    def _to_broker_order(self, order: Order) -> dict[str, Any]:
        """Map a platform :class:`Order` to a Schwab/TDA order JSON body.

        Mirrors the documented ``POST /accounts/{id}/orders`` schema: a single
        ``orderLegCollection`` leg for an equity instrument.
        """
        instruction = "BUY" if order.side == OrderSide.BUY else "SELL"
        body: dict[str, Any] = {
            "orderType": _TYPE_TO_TDA.get(order.order_type, "MARKET"),
            "session": "NORMAL",
            "duration": _TIF_TO_TDA.get(order.time_in_force, "DAY"),
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": order.quantity,
                    "instrument": {
                        "symbol": order.symbol,
                        "assetType": "EQUITY",
                    },
                }
            ],
        }
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            body["price"] = order.limit_price
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            body["stopPrice"] = order.stop_price
        return body

    def _from_broker_order(self, data: dict[str, Any],
                           order: Order | None = None) -> Order:
        """Map a Schwab/TDA order payload back into a platform :class:`Order`."""
        legs = data.get("orderLegCollection") or [{}]
        leg = legs[0]
        instrument = leg.get("instrument", {}) or {}
        instruction = (leg.get("instruction") or "BUY").upper()
        side = OrderSide.BUY if instruction.startswith("BUY") else OrderSide.SELL
        result = order or Order(
            symbol=instrument.get("symbol", ""),
            side=side,
            quantity=float(leg.get("quantity") or data.get("quantity") or 0.0),
            order_type=_TYPE_FROM_TDA.get(data.get("orderType", "MARKET"), OrderType.MARKET),
        )
        result.broker_order_id = str(data.get("orderId", ""))
        result.status = _STATUS_FROM_TDA.get(data.get("status", ""), OrderStatus.SUBMITTED)
        result.filled_quantity = float(data.get("filledQuantity") or 0.0)
        result.account_id = self._account_id
        return result

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        """Authenticate against the Schwab Trader API.

        Building the session validates that an OAuth token is present. Confirming
        the session against ``GET /accounts`` is left to the caller because the
        Schwab response schema must be verified against live docs first.
        """
        self._session = self._build_session()
        self._connected = True
        logger.info("TDAmeritradeBroker session prepared (%s)", self.base_url)

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.close()
        self._session = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _not_live(self, what: str) -> NotImplementedError:
        return NotImplementedError(f"{what} is not wired for live trading. " + _MIGRATION_HINT)

    # --- orders ---------------------------------------------------------
    def submit_order(self, order: Order) -> Order:
        # Real shape: POST {base}/accounts/{account_id}/orders with
        # self._to_broker_order(order); Schwab returns the order id in the
        # Location header rather than a JSON body.
        raise self._not_live("submit_order")

    def cancel_order(self, order_id: str) -> bool:
        # Real shape: DELETE {base}/accounts/{account_id}/orders/{order_id}
        raise self._not_live("cancel_order")

    def get_order(self, order_id: str) -> Order | None:
        # Real shape: GET {base}/accounts/{account_id}/orders/{order_id}
        raise self._not_live("get_order")

    def get_open_orders(self) -> list[Order]:
        # Real shape: GET {base}/accounts/{account_id}/orders?status=WORKING
        raise self._not_live("get_open_orders")

    # --- account / positions -------------------------------------------
    def get_account(self) -> AccountSnapshot:
        # Real shape: GET {base}/accounts/{account_id} -> securitiesAccount block
        raise self._not_live("get_account")

    def get_positions(self) -> list[Position]:
        # Real shape: GET {base}/accounts/{account_id}?fields=positions
        raise self._not_live("get_positions")
