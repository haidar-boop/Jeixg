"""Webull broker adapter (UNOFFICIAL).

.. warning::
   This adapter relies on the community-maintained, **unofficial** ``webull``
   Python package, which reverse-engineers Webull's private mobile/web API.
   Automated trading via unofficial endpoints may violate Webull's Terms of
   Service and can break without notice. Use only for research/paper purposes
   and at your own risk.

The dependency is imported lazily so the platform runs without it.
"""
from __future__ import annotations

from ..core.exceptions import BrokerConnectionError
from ..core.logging_config import get_logger
from ..core.security import SecretVault
from ..models import AccountSnapshot, Order, Position
from .base import Broker

logger = get_logger(__name__)


class WebullBroker(Broker):
    """Thin scaffold over the unofficial ``webull`` library."""

    name = "webull"
    supports_shorting = False

    def __init__(self, vault: SecretVault | None = None) -> None:
        self._wb = None
        self._connected = False
        self._vault = vault or SecretVault()

    def _require_lib(self):
        try:
            from webull import webull  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional
            raise BrokerConnectionError(
                "Webull support requires `pip install webull` (unofficial)."
            ) from exc
        return webull

    def connect(self) -> None:
        webull = self._require_lib()
        creds = self._vault.get_broker_credentials("webull")
        self._wb = webull()
        # login() signature varies by lib version; documented for reference.
        self._wb.login(creds.api_key, creds.api_secret)
        self._connected = True
        logger.info("Webull session established (unofficial API)")

    def disconnect(self) -> None:
        self._connected = False
        self._wb = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def submit_order(self, order: Order) -> Order:  # pragma: no cover - needs live creds
        raise NotImplementedError(
            "Map Order -> webull.place_order here once credentials are configured."
        )

    def cancel_order(self, order_id: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def get_order(self, order_id: str) -> Order | None:  # pragma: no cover
        raise NotImplementedError

    def get_open_orders(self) -> list[Order]:  # pragma: no cover
        raise NotImplementedError

    def get_account(self) -> AccountSnapshot:  # pragma: no cover
        raise NotImplementedError

    def get_positions(self) -> list[Position]:  # pragma: no cover
        raise NotImplementedError
