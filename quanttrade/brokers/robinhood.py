"""Robinhood broker adapter (via the unofficial ``robin_stocks`` library).

.. warning::
    **UNOFFICIAL / USE AT YOUR OWN RISK.** Robinhood does *not* publish a
    public trading API. This adapter relies on the third-party, reverse
    engineered ``robin_stocks`` library which drives Robinhood's private
    web/mobile endpoints. Automated trading may violate Robinhood's Terms of
    Service, can break without notice when those private endpoints change, and
    frequently triggers MFA / device-approval challenges. Do not use this for
    anything you are not prepared to lose access to.

Library: https://github.com/jmfernandes/robin_stocks
Install: ``pip install robin_stocks``

How it works
------------
``robin_stocks.robinhood`` is a *module of functions* (not a client object).
Authentication is stateful and global to the process::

    import robin_stocks.robinhood as rh
    rh.login(username, password, mfa_code=...)
    rh.orders.order_buy_market("AAPL", 1)
    rh.account.build_holdings()
    rh.logout()

Credentials come from ``SecretVault().get_broker_credentials("robinhood")`` where
``api_key`` is the username/email and ``api_secret`` the password. An optional
TOTP/MFA secret can be supplied via the constructor.
"""
from __future__ import annotations

import warnings
from typing import Any

from ..core.enums import OrderSide, OrderStatus, OrderType
from ..core.exceptions import BrokerConnectionError, OrderRejectedError
from ..core.logging_config import get_logger
from ..core.security import SecretVault
from ..models import AccountSnapshot, Order, Position
from .base import Broker

logger = get_logger(__name__)

_UNOFFICIAL_WARNING = (
    "RobinhoodBroker uses the UNOFFICIAL 'robin_stocks' library against private "
    "Robinhood endpoints. This may violate Robinhood's Terms of Service and can "
    "break without notice."
)

# Robinhood order state -> platform OrderStatus
_STATUS_FROM_RH = {
    "queued": OrderStatus.PENDING,
    "unconfirmed": OrderStatus.PENDING,
    "confirmed": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "rejected": OrderStatus.REJECTED,
    "cancelled": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,
    "failed": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
}


class RobinhoodBroker(Broker):
    """Robinhood adapter backed by the unofficial ``robin_stocks`` library."""

    name = "robinhood"
    supports_fractional = True
    supports_shorting = False  # Robinhood does not support shorting.

    def __init__(self, mfa_secret: str | None = None) -> None:
        warnings.warn(_UNOFFICIAL_WARNING, UserWarning, stacklevel=2)
        self.mfa_secret = mfa_secret
        self._rh: Any = None
        self._connected = False
        self._account_id = ""

    # --- internals ------------------------------------------------------
    def _require_rh(self):
        """Lazily import ``robin_stocks``; raise a clear install hint if missing."""
        try:
            import robin_stocks.robinhood as rh  # noqa: PLC0415
        except ImportError as exc:
            raise BrokerConnectionError(
                "RobinhoodBroker requires the unofficial 'robin_stocks' library. "
                "Install it with: pip install robin_stocks"
            ) from exc
        return rh

    def _mfa_code(self) -> str | None:
        """Derive a current TOTP code from ``mfa_secret`` if pyotp is available."""
        if not self.mfa_secret:
            return None
        try:
            import pyotp  # noqa: PLC0415
        except ImportError:  # pragma: no cover - optional
            return None
        return pyotp.TOTP(self.mfa_secret).now()

    # --- mapping --------------------------------------------------------
    def _to_broker_order(self, order: Order) -> dict[str, Any]:
        """Map a platform :class:`Order` to ``robin_stocks`` order kwargs.

        Returns a dict identifying the right ``rh.orders.order_*`` function and
        its arguments; :meth:`submit_order` dispatches on it.
        """
        is_buy = order.side == OrderSide.BUY
        params: dict[str, Any] = {
            "symbol": order.symbol,
            "quantity": order.quantity,
        }
        if order.order_type == OrderType.MARKET:
            params["fn"] = "order_buy_market" if is_buy else "order_sell_market"
        elif order.order_type == OrderType.LIMIT:
            params["fn"] = "order_buy_limit" if is_buy else "order_sell_limit"
            params["limitPrice"] = order.limit_price
        elif order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if order.order_type == OrderType.STOP:
                params["fn"] = "order_buy_stop_loss" if is_buy else "order_sell_stop_loss"
            else:
                params["fn"] = "order_buy_stop_limit" if is_buy else "order_sell_stop_limit"
                params["limitPrice"] = order.limit_price
            params["stopPrice"] = order.stop_price
        else:
            params["fn"] = "order_buy_market" if is_buy else "order_sell_market"
        return params

    def _from_broker_order(self, data: dict[str, Any],
                           order: Order | None = None) -> Order:
        """Map a ``robin_stocks`` order payload back into a platform :class:`Order`."""
        side = OrderSide.BUY if (data.get("side") == "buy") else OrderSide.SELL
        qty = float(data.get("quantity") or 0.0)
        result = order or Order(
            symbol=data.get("symbol") or data.get("instrument", ""),
            side=side,
            quantity=qty,
        )
        result.broker_order_id = str(data.get("id", ""))
        result.status = _STATUS_FROM_RH.get(
            (data.get("state") or "").lower(), OrderStatus.SUBMITTED
        )
        result.filled_quantity = float(data.get("cumulative_quantity") or 0.0)
        avg = data.get("average_price")
        result.avg_fill_price = float(avg) if avg else 0.0
        result.account_id = self._account_id
        return result

    # --- lifecycle ------------------------------------------------------
    def connect(self) -> None:
        """Log in via ``rh.login(...)`` using vault credentials."""
        self._rh = self._require_rh()
        creds = SecretVault().get_broker_credentials(self.name)
        self._account_id = creds.account_id
        try:
            self._rh.login(
                username=creds.api_key,
                password=creds.api_secret,
                mfa_code=self._mfa_code(),
            )
        except Exception as exc:  # noqa: BLE001 - robin_stocks raises broadly
            self._rh = None
            raise BrokerConnectionError(f"Robinhood login failed: {exc}") from exc
        self._connected = True
        logger.warning("Connected to Robinhood (UNOFFICIAL API)")

    def disconnect(self) -> None:
        if self._rh is not None:
            try:
                self._rh.logout()
            except Exception:  # pragma: no cover - defensive
                pass
        self._rh = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _check(self):
        if not self._connected or self._rh is None:
            raise BrokerConnectionError("RobinhoodBroker is not connected; call connect()")
        return self._rh

    # --- orders ---------------------------------------------------------
    def submit_order(self, order: Order) -> Order:
        rh = self._check()
        params = self._to_broker_order(order)
        fn_name = params.pop("fn")
        fn = getattr(rh.orders, fn_name, None) or getattr(rh, fn_name, None)
        if fn is None:  # pragma: no cover - depends on robin_stocks version
            raise OrderRejectedError(f"robin_stocks has no order function '{fn_name}'")
        try:
            data = fn(**params)
        except Exception as exc:  # noqa: BLE001
            raise OrderRejectedError(f"Robinhood rejected order: {exc}") from exc
        if not data or "id" not in data:
            raise OrderRejectedError(f"Robinhood order failed: {data}")
        return self._from_broker_order(data, order)

    def cancel_order(self, order_id: str) -> bool:
        rh = self._check()
        try:
            rh.orders.cancel_stock_order(order_id)
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_order(self, order_id: str) -> Order | None:
        rh = self._check()
        try:
            data = rh.orders.get_stock_order_info(order_id)
        except Exception:  # noqa: BLE001
            return None
        return self._from_broker_order(data) if data else None

    def get_open_orders(self) -> list[Order]:
        rh = self._check()
        orders = rh.orders.get_all_open_stock_orders() or []
        return [self._from_broker_order(o) for o in orders]

    # --- account / positions -------------------------------------------
    def get_account(self) -> AccountSnapshot:
        rh = self._check()
        profile = rh.profiles.load_account_profile() or {}
        portfolio = rh.profiles.load_portfolio_profile() or {}
        cash = float(profile.get("cash") or profile.get("buying_power") or 0.0)
        equity = float(portfolio.get("equity") or portfolio.get("extended_hours_equity") or 0.0)
        return AccountSnapshot(
            cash=cash,
            equity=equity,
            buying_power=float(profile.get("buying_power") or 0.0),
            positions_value=float(portfolio.get("market_value") or 0.0),
            account_id=self._account_id or profile.get("account_number", "default"),
        )

    def get_positions(self) -> list[Position]:
        rh = self._check()
        holdings = rh.account.build_holdings() or {}
        positions: list[Position] = []
        for symbol, h in holdings.items():
            positions.append(Position(
                symbol=symbol,
                quantity=float(h.get("quantity") or 0.0),
                avg_price=float(h.get("average_buy_price") or 0.0),
                last_price=float(h.get("price") or 0.0),
            ))
        return positions
