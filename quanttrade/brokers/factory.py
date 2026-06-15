"""Broker factory -- create brokers by name (config-driven multi-broker support)."""
from __future__ import annotations

from .base import Broker

_ALIASES = {
    "paper": "paper",
    "sim": "paper",
    "alpaca": "alpaca",
    "ibkr": "interactive_brokers",
    "ib": "interactive_brokers",
    "interactive_brokers": "interactive_brokers",
    "tradier": "tradier",
    "td": "td_ameritrade",
    "tda": "td_ameritrade",
    "td_ameritrade": "td_ameritrade",
    "schwab": "td_ameritrade",
    "robinhood": "robinhood",
    "webull": "webull",
    "generic": "generic",
}


def list_brokers() -> list[str]:
    """Return the canonical broker names this platform can construct."""
    return sorted(set(_ALIASES.values()))


def create_broker(name: str, **kwargs) -> Broker:
    """Instantiate a broker adapter by name or alias.

    Adapters are imported lazily so that a missing optional broker SDK never
    breaks ``import quanttrade.brokers``.
    """
    key = _ALIASES.get(name.lower())
    if key is None:
        raise ValueError(f"Unknown broker '{name}'. Available: {list(_ALIASES)}")

    if key == "paper":
        from .paper import PaperBroker
        return PaperBroker(**kwargs)
    if key == "alpaca":
        from .alpaca import AlpacaBroker
        return AlpacaBroker(**kwargs)
    if key == "interactive_brokers":
        from .interactive_brokers import InteractiveBrokersBroker
        return InteractiveBrokersBroker(**kwargs)
    if key == "tradier":
        from .tradier import TradierBroker
        return TradierBroker(**kwargs)
    if key == "td_ameritrade":
        from .td_ameritrade import TDAmeritradeBroker
        return TDAmeritradeBroker(**kwargs)
    if key == "robinhood":
        from .robinhood import RobinhoodBroker
        return RobinhoodBroker(**kwargs)
    if key == "webull":
        from .webull import WebullBroker
        return WebullBroker(**kwargs)
    if key == "generic":
        from .generic import GenericRESTBroker
        return GenericRESTBroker(**kwargs)
    raise ValueError(f"Unhandled broker key '{key}'")  # pragma: no cover
