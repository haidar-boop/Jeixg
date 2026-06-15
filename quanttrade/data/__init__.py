"""Market data layer: providers, caching and a config-driven factory."""
from __future__ import annotations

from ..core.config import get_config
from .base import MarketDataProvider
from .providers.synthetic import SyntheticDataProvider

__all__ = ["MarketDataProvider", "SyntheticDataProvider", "create_data_provider"]


def create_data_provider(name: str | None = None, **kwargs) -> MarketDataProvider:
    """Instantiate a market-data provider by name.

    Falls back to the synthetic provider if an optional provider's dependency is
    unavailable, so the platform always has a working data source.
    """
    name = (name or get_config().get("data.provider", "synthetic")).lower()
    if name in {"synthetic", "sim", "test"}:
        return SyntheticDataProvider(**kwargs)
    if name in {"yfinance", "yahoo"}:
        from ..core.logging_config import get_logger
        from .providers.yfinance_provider import YFinanceDataProvider

        try:
            return YFinanceDataProvider()
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning(
                "yfinance unavailable (%s); falling back to synthetic provider", exc
            )
            return SyntheticDataProvider(**kwargs)
    raise ValueError(f"Unknown data provider '{name}'")
