"""Exception hierarchy for QuantTrade.

A single rooted hierarchy lets callers catch broad categories
(``QuantTradeError``) or specific failures (``OrderRejectedError``) and lets
the recovery layer apply differentiated retry/back-off policies.
"""
from __future__ import annotations


class QuantTradeError(Exception):
    """Base class for all platform errors."""


class ConfigError(QuantTradeError):
    """Raised when configuration is missing or invalid."""


# --- Data layer ---------------------------------------------------------
class DataError(QuantTradeError):
    """Base for market-data failures."""


class DataNotAvailableError(DataError):
    """Requested symbol / range is not available from a provider."""


class DataProviderError(DataError):
    """A provider failed (network, auth, rate limit)."""


# --- Broker / execution -------------------------------------------------
class BrokerError(QuantTradeError):
    """Base for broker-side failures."""


class BrokerConnectionError(BrokerError):
    """Could not connect to / authenticate with a broker."""


class OrderRejectedError(BrokerError):
    """Broker rejected an order (e.g. insufficient buying power)."""


class InsufficientFundsError(OrderRejectedError):
    """Not enough buying power / margin to place the order."""


# --- Risk ---------------------------------------------------------------
class RiskError(QuantTradeError):
    """Base for risk-management failures."""


class RiskLimitBreached(RiskError):
    """A pre-trade or portfolio risk limit was breached."""

    def __init__(self, rule: str, message: str) -> None:
        self.rule = rule
        super().__init__(f"[{rule}] {message}")


# --- Strategy -----------------------------------------------------------
class StrategyError(QuantTradeError):
    """Strategy raised an unrecoverable error."""


class SecurityError(QuantTradeError):
    """Authentication / authorisation / credential failure."""
