"""Broker layer: a common interface, a paper-trading engine and live adapters.

Live adapters are imported lazily through :func:`create_broker` so missing
optional SDKs (ib_insync, robin_stocks, webull, ...) never break importing this
package.
"""
from .base import Broker
from .factory import create_broker, list_brokers
from .paper import PaperBroker

__all__ = ["Broker", "PaperBroker", "create_broker", "list_brokers"]
