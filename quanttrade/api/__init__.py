"""Web API layer (FastAPI). Optional dependency: imported lazily."""
from .service import PlatformService


def create_app(service=None):
    """Lazy wrapper so importing :mod:`quanttrade.api` never requires FastAPI."""
    from .app import create_app as _create_app
    return _create_app(service)


__all__ = ["PlatformService", "create_app"]
