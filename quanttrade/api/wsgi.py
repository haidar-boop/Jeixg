"""WSGI (Flask) entry point for PythonAnywhere and other WSGI hosts.

PythonAnywhere serves **WSGI** apps only -- it cannot run the FastAPI/ASGI app
or WebSockets. This module exposes the same REST API as ``app.py`` using Flask,
plus optionally serves the built React dashboard (``dashboard/dist``) from the
same origin, so the whole thing works behind one PythonAnywhere web app.

The PA WSGI config file should point at the module-level ``application`` object::

    from quanttrade.api.wsgi import application

Heavy endpoints (predictions, scanner) are cached with a short TTL so page loads
stay fast.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..core.logging_config import get_logger
from .service import PlatformService

logger = get_logger(__name__)

# Default location of the built React dashboard (run `npm run build`).
DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


def create_wsgi_app(service: PlatformService | None = None, dist_dir: Path | None = None):
    """Build the Flask WSGI application."""
    try:
        from flask import Flask, jsonify, request, send_from_directory
    except ImportError as exc:  # pragma: no cover - optional
        raise ImportError("The WSGI dashboard requires Flask. Run `pip install flask`.") from exc

    service = service or PlatformService()
    dist_dir = dist_dir or DASHBOARD_DIST
    cache: dict[str, tuple[float, object]] = {}
    CACHE_TTL = 60.0  # seconds

    app = Flask(__name__, static_folder=None)

    def cached(key: str, producer):
        now = time.time()
        hit = cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
        value = producer()
        cache[key] = (now, value)
        return value

    def _ensure_bootstrap():
        if service._result is None:
            service.bootstrap_demo()

    # --- REST API (mirrors the FastAPI routes) --------------------------
    @app.get("/api/health")
    def health():
        return jsonify(service.health())

    @app.get("/api/portfolio")
    def portfolio():
        _ensure_bootstrap()
        return jsonify(service.portfolio())

    @app.get("/api/positions")
    def positions():
        _ensure_bootstrap()
        return jsonify(service.positions())

    @app.get("/api/trades")
    def trades():
        _ensure_bootstrap()
        limit = request.args.get("limit", default=100, type=int)
        return jsonify(service.trades(limit))

    @app.get("/api/equity_curve")
    def equity_curve():
        _ensure_bootstrap()
        return jsonify(service.equity_curve())

    @app.get("/api/strategies")
    def strategies():
        _ensure_bootstrap()
        return jsonify(service.strategies())

    @app.get("/api/risk")
    def risk():
        _ensure_bootstrap()
        return jsonify(service.risk())

    @app.get("/api/predictions")
    def predictions():
        return jsonify(cached("predictions", service.predictions))

    @app.get("/api/scanner")
    def scanner():
        top_n = request.args.get("top_n", default=10, type=int)
        return jsonify(cached(f"scanner:{top_n}", lambda: service.scanner(top_n)))

    # --- Serve the built React SPA (if present) -------------------------
    @app.get("/")
    @app.get("/<path:path>")
    def spa(path: str = ""):  # noqa: ANN001
        if not dist_dir.exists():
            return (
                "<h1>QuantTrade API</h1><p>REST API is live at <code>/api/health</code>. "
                "Build the dashboard with <code>cd dashboard &amp;&amp; npm run build</code> "
                "to serve the UI here.</p>",
                200,
            )
        target = dist_dir / path
        if path and target.is_file():
            return send_from_directory(dist_dir, path)
        return send_from_directory(dist_dir, "index.html")  # SPA fallback

    return app


# Module-level WSGI callable expected by PythonAnywhere / gunicorn.
try:  # pragma: no cover - only when Flask is installed
    application = create_wsgi_app()
except ImportError:
    application = None
