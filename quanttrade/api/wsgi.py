"""WSGI (Flask) entry point for PythonAnywhere and other WSGI hosts.

PythonAnywhere serves **WSGI** apps only -- it cannot run the FastAPI/ASGI app
or WebSockets. This module exposes the dashboard's REST API using Flask and
serves the built React app from the same origin.

If a live broker (e.g. Alpaca) is configured with valid credentials, the
dashboard shows your **real account** (positions, P&L, orders, equity curve,
market status, per-symbol signals). Otherwise it falls back to a self-contained
demo so the page still works.

Point your PythonAnywhere WSGI config file at the module-level ``application``.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from ..core.config import _load_dotenv, get_config
from ..core.logging_config import get_logger
from .service import PlatformService

logger = get_logger(__name__)


def _clean(obj):
    """Replace NaN/Infinity (invalid JSON, breaks browsers) with null."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIST = PROJECT_ROOT / "dashboard" / "dist"
LIVE_BROKERS = {"alpaca", "tradier", "interactive_brokers", "ibkr"}
DEFAULT_SYMBOLS = (
    "AAPL,MSFT,GOOG,AMZN,NVDA,TSLA,META,AMD,NFLX,JPM,V,WMT,XOM,SPY,QQQ,"
    "AVGO,COST,HD,BAC,DIS,PYPL,INTC,CRM,PFE,KO,PEP,CSCO,ORCL,ADBE,QCOM,"
    "UBER,SHOP,COIN,PLTR,SOFI,BA,GE,F,T,MU"
)

# Endpoints whose results are expensive to compute -> cache briefly.
CACHE_TTL = 30.0
HEAVY = {"watchlist", "predictions", "scanner", "equity_curve"}


def _build_service():
    """Build a live broker-backed service if configured, else the demo service."""
    import os

    _load_dotenv(PROJECT_ROOT / ".env")
    cfg = get_config(reload=True)
    broker_name = (os.getenv("QT_BROKER__NAME") or cfg.get("broker.name", "paper")).lower()
    provider = os.getenv("QT_DATA__PROVIDER") or cfg.get("data.provider", "synthetic")
    symbols = [s.strip().upper() for s in
               (os.getenv("QT_SYMBOLS") or DEFAULT_SYMBOLS).split(",") if s.strip()]
    strategy = os.getenv("QT_STRATEGY") or cfg.get("trading.strategy", "ma_crossover")

    if broker_name in LIVE_BROKERS:
        try:
            from ..brokers import create_broker
            from ..data import create_data_provider
            from ..risk import RiskLimits
            from .live_service import LivePlatformService

            broker = create_broker(broker_name)
            broker.connect()
            svc = LivePlatformService(broker, create_data_provider(provider), symbols,
                                      strategy, RiskLimits.from_config(cfg))
            logger.info("Dashboard in LIVE mode via %s (%d symbols)", broker_name, len(symbols))
            return svc
        except Exception:  # noqa: BLE001
            logger.exception("Live dashboard init failed; falling back to demo")

    demo = PlatformService(symbols)
    return demo


def _twiml(message: str):
    """Build a Twilio TwiML SMS reply response."""
    from flask import Response

    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<Response><Message>{message}</Message></Response>')
    return Response(xml, mimetype="text/xml")


def create_wsgi_app(service=None, dist_dir: Path | None = None):
    """Build the Flask WSGI application."""
    try:
        from flask import Flask, jsonify, request, send_from_directory
    except ImportError as exc:  # pragma: no cover - optional
        raise ImportError("The WSGI dashboard requires Flask. Run `pip install flask`.") from exc

    service = service or _build_service()
    dist_dir = dist_dir or DASHBOARD_DIST
    cache: dict[str, tuple[float, object]] = {}

    app = Flask(__name__, static_folder=None)

    def serve(name: str, *args, **kwargs):
        """Call a service method by name, with light caching + demo fallback."""
        fn = getattr(service, name, None)
        if fn is None:
            return jsonify([] if name in {"positions", "orders", "trades", "watchlist",
                                          "equity_curve", "predictions", "scanner",
                                          "strategies"} else {})
        key = name + repr(args) + repr(kwargs)
        if name in HEAVY:
            hit = cache.get(key)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return jsonify(hit[1])
        try:
            value = fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - never 500 the dashboard
            logger.exception("Endpoint %s failed", name)
            value = [] if name != "account" else {}
        if name in HEAVY:
            cache[key] = (time.time(), value)
        return jsonify(_clean(value))

    # --- REST API -------------------------------------------------------
    @app.get("/api/health")
    def health():
        return serve("health")

    @app.get("/api/account")
    def account():
        return serve("account")

    @app.get("/api/portfolio")
    def portfolio():
        return serve("portfolio")

    @app.get("/api/positions")
    def positions():
        return serve("positions")

    @app.get("/api/orders")
    def orders():
        return serve("orders", request.args.get("limit", 50, type=int))

    @app.get("/api/trades")
    def trades():
        return serve("trades", request.args.get("limit", 50, type=int))

    @app.get("/api/equity_curve")
    def equity_curve():
        return serve("equity_curve")

    @app.get("/api/watchlist")
    def watchlist():
        # Prefer the snapshot the bot writes (reliable); fall back to computing.
        from .snapshot import read_watchlist
        rows = read_watchlist()
        if rows is not None:
            return jsonify(_clean(rows))
        return serve("watchlist")

    @app.get("/api/clock")
    def clock():
        return serve("clock")

    @app.get("/api/strategies")
    def strategies():
        return serve("strategies")

    @app.get("/api/risk")
    def risk():
        return serve("risk")

    @app.get("/api/predictions")
    def predictions():
        return serve("predictions")

    @app.get("/api/scanner")
    def scanner():
        return serve("scanner", request.args.get("top_n", 15, type=int))

    # --- Twilio inbound SMS webhook (two-way trade approval) -----------
    @app.post("/sms")
    def sms_webhook():
        import os

        from ..notifications.approvals import ApprovalStore, parse_reply

        from_number = request.form.get("From", "")
        body = request.form.get("Body", "")
        allowed = os.getenv("QT_TWILIO_TO", "")
        # Only accept commands from the owner's verified phone number.
        if allowed and from_number and from_number != allowed:
            logger.warning("Ignoring SMS from unauthorized number %s", from_number)
            return _twiml("Sorry, this number isn't authorized.")

        decision, symbol = parse_reply(body)
        text = (body or "").strip().lower()

        # Control commands take priority over yes/no.
        from ..notifications.control import ControlStore
        ctrl = ControlStore()
        if text in {"stop", "halt", "pause"}:
            ctrl.set_halt(True)
            return _twiml("⏸ Trading paused. Text RESUME to start again, or SELL ALL to close everything.")
        if text in {"resume", "start", "go", "unpause"}:
            ctrl.set_halt(False)
            return _twiml("▶️ Trading resumed.")
        if text in {"sell all", "sellall", "flatten", "close all", "closeall"}:
            ctrl.request_flatten()
            ctrl.set_halt(True)  # pause immediately so it can't re-buy before flattening
            return _twiml("Selling all positions and pausing. Text RESUME to start trading again.")

        if decision is None:
            return _twiml("Reply YES/NO to a stock I found, or STOP / RESUME / SELL ALL.")
        req = ApprovalStore().record_decision(decision, symbol)
        if req is None:
            return _twiml("No trade is waiting for approval right now.")
        if decision:
            return _twiml(f"Got it — buying {req['symbol']} on the next check. ✅")
        return _twiml(f"Okay, skipping {req['symbol']}. 👍")

    # --- Serve the built React SPA -------------------------------------
    @app.get("/")
    @app.get("/<path:path>")
    def spa(path: str = ""):  # noqa: ANN001
        if not dist_dir.exists():
            return ("<h1>QuantTrade API</h1><p>REST API is live at "
                    "<code>/api/health</code>. Build the dashboard with "
                    "<code>cd dashboard &amp;&amp; npm run build</code> to serve the UI.</p>", 200)
        target = dist_dir / path
        if path and target.is_file():
            return send_from_directory(dist_dir, path)
        return send_from_directory(dist_dir, "index.html")

    return app


# Module-level WSGI callable expected by PythonAnywhere / gunicorn.
try:  # pragma: no cover - only when Flask is installed
    application = create_wsgi_app()
except ImportError:
    application = None
