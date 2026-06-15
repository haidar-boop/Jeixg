"""FastAPI application factory.

Exposes the REST + WebSocket API consumed by the React dashboard. FastAPI is an
optional dependency imported here (not at package import time) so the core
platform installs/runs without the web stack.

Run with::

    uvicorn quanttrade.api.app:app --reload
    # or
    python -m quanttrade.cli serve
"""
from __future__ import annotations

import asyncio
import json

from ..core.config import get_config
from ..core.logging_config import get_logger
from .service import PlatformService

logger = get_logger(__name__)


def create_app(service: PlatformService | None = None):
    """Build and return a configured FastAPI application."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - optional
        raise ImportError("The API requires FastAPI. Run `pip install fastapi uvicorn`.") from exc

    cfg = get_config()
    service = service or PlatformService()

    app = FastAPI(title="QuantTrade API", version="0.1.0",
                  description="Algorithmic trading platform API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.get("api.cors_origins", ["*"]),
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - runtime
        if service._result is None:
            await asyncio.to_thread(service.bootstrap_demo)

    # --- REST -----------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict:
        return service.health()

    @app.get("/api/portfolio")
    def portfolio() -> dict:
        return service.portfolio()

    @app.get("/api/positions")
    def positions() -> list[dict]:
        return service.positions()

    @app.get("/api/trades")
    def trades(limit: int = 100) -> list[dict]:
        return service.trades(limit)

    @app.get("/api/equity_curve")
    def equity_curve() -> list[dict]:
        return service.equity_curve()

    @app.get("/api/strategies")
    def strategies() -> list[dict]:
        return service.strategies()

    @app.get("/api/risk")
    def risk() -> dict:
        return service.risk()

    @app.get("/api/predictions")
    def predictions() -> list[dict]:
        return service.predictions()

    @app.get("/api/scanner")
    def scanner(top_n: int = 10) -> list[dict]:
        return service.scanner(top_n)

    # --- WebSocket: push live portfolio/positions snapshots -------------
    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:  # pragma: no cover - runtime
        await websocket.accept()
        try:
            while True:
                payload = {
                    "type": "snapshot",
                    "data": {
                        "portfolio": service.portfolio(),
                        "positions": service.positions(),
                    },
                }
                await websocket.send_text(json.dumps(payload))
                await asyncio.sleep(2.0)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")

    return app


# Module-level app for `uvicorn quanttrade.api.app:app`.
try:  # pragma: no cover - only when fastapi is installed
    app = create_app()
except ImportError:
    app = None
