"""Web API layer. Optional web deps (FastAPI / Flask) are imported lazily."""
from .service import PlatformService


def create_app(service=None):
    """Lazy wrapper so importing :mod:`quanttrade.api` never requires FastAPI."""
    from .app import create_app as _create_app
    return _create_app(service)


def create_wsgi_app(service=None):
    """Lazy wrapper for the Flask WSGI app (PythonAnywhere / gunicorn)."""
    from .wsgi import create_wsgi_app as _create_wsgi_app
    return _create_wsgi_app(service)


__all__ = ["PlatformService", "create_app", "create_wsgi_app"]
