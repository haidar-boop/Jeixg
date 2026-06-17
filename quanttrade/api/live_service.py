"""Live dashboard service.

Unlike :class:`PlatformService` (which runs a demo backtest), this service reads
**real** state from a connected broker (e.g. your Alpaca paper account) and pairs
it with live analytics, so the dashboard shows your actual account:

* account summary (equity, cash, buying power, day P&L)
* live open positions with unrealized P&L
* recent order activity
* the real equity curve (broker portfolio history)
* market status (open/closed, next open/close)
* a watchlist showing the bot's current signal + indicators for each symbol
* market scanner, AI predictions and risk metrics

It degrades gracefully: any piece that a given broker doesn't support simply
returns empty rather than erroring, so the page always renders.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from ..brokers.base import Broker
from ..core.enums import BarInterval, OrderStatus, SignalType
from ..core.logging_config import get_logger
from ..data.base import MarketDataProvider
from ..indicators import rsi
from ..indicators.structure import detect_trend
from ..risk import RiskLimits
from ..scanner import MarketScanner
from ..strategies import StrategyRegistry
from ..strategies.base import StrategyContext

logger = get_logger(__name__)


class LivePlatformService:
    """Serves live broker + analytics data to the dashboard."""

    def __init__(self, broker: Broker, provider: MarketDataProvider, symbols: list[str],
                 strategy_name: str = "ma_crossover", risk_limits: RiskLimits | None = None):
        self.broker = broker
        self.provider = provider
        self.symbols = symbols
        self.strategy_name = strategy_name
        self.risk_limits = risk_limits or RiskLimits()
        self._all_bars_cache: dict | None = None
        self._all_bars_ts: float = 0.0
        # Heavy results are cached so the dashboard never blocks on recompute.
        self._cache: dict[str, tuple[float, object]] = {}

    # --- helpers --------------------------------------------------------
    def _ensure_connected(self) -> None:
        if not self.broker.is_connected:
            self.broker.connect()

    def _all_bars(self, days: int = 260) -> dict:
        """One cached batch fetch of daily bars for the whole symbol list.

        Shared by the watchlist, scanner and predictions so a dashboard refresh
        makes a single data request (not one per symbol), refreshed every 5 min.
        """
        if self._all_bars_cache is not None and (time.time() - self._all_bars_ts) < 300:
            return self._all_bars_cache
        end = datetime.now(timezone.utc)
        self._all_bars_cache = self.provider.get_multiple(
            self.symbols, end - timedelta(days=days), end, BarInterval.DAY_1)
        self._all_bars_ts = time.time()
        return self._all_bars_cache

    def _cached(self, key: str, ttl: float, producer):
        hit = self._cache.get(key)
        if hit and (time.time() - hit[0]) < ttl:
            return hit[1]
        value = producer()
        self._cache[key] = (time.time(), value)
        return value

    def _positions_map(self) -> dict:
        self._ensure_connected()
        return {p.symbol: p for p in self.broker.get_positions()}

    # --- account / portfolio -------------------------------------------
    def health(self) -> dict:
        connected = False
        try:
            self._ensure_connected()
            connected = self.broker.is_connected
        except Exception:  # noqa: BLE001
            connected = False
        return {"status": "ok", "mode": "live", "broker": self.broker.name,
                "broker_connected": connected, "symbols": self.symbols,
                "strategy": self.strategy_name}

    def account(self) -> dict:
        self._ensure_connected()
        acct = self.broker.get_account()
        raw = self.broker.get_account_raw() if hasattr(self.broker, "get_account_raw") else {}
        positions = self.broker.get_positions()
        last_equity = float(raw.get("last_equity") or acct.equity)
        day_pnl = acct.equity - last_equity
        unrealized = sum(p.unrealized_pnl for p in positions)
        return {
            "equity": round(acct.equity, 2),
            "cash": round(acct.cash, 2),
            "buying_power": round(acct.buying_power, 2),
            "positions_value": round(acct.positions_value, 2),
            "day_pnl": round(day_pnl, 2),
            "day_pnl_pct": round(day_pnl / last_equity, 4) if last_equity else 0.0,
            "unrealized_pnl": round(unrealized, 2),
            "num_positions": len(positions),
            "status": raw.get("status", "ACTIVE"),
            "pattern_day_trader": bool(raw.get("pattern_day_trader", False)),
        }

    def portfolio(self) -> dict:
        """Compatibility shape for the summary cards."""
        a = self.account()
        return {
            "equity": a["equity"], "cash": a["cash"],
            "positions_value": a["positions_value"], "day_pnl": a["day_pnl"],
            "total_pnl": a["unrealized_pnl"],
        }

    def positions(self) -> list[dict]:
        self._ensure_connected()
        out = []
        for p in self.broker.get_positions():
            cost = p.avg_price * abs(p.quantity)
            out.append({
                "symbol": p.symbol,
                "quantity": round(p.quantity, 4),
                "avg_price": round(p.avg_price, 2),
                "last_price": round(p.last_price, 2),
                "market_value": round(p.market_value, 2),
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "unrealized_pct": round(p.unrealized_pnl / cost, 4) if cost else 0.0,
                "side": p.side.value,
            })
        return out

    def orders(self, limit: int = 50, include_inactive: bool = False) -> list[dict]:
        """Orders straight from the broker. Cancelled/expired/rejected orders are
        hidden by default, so deleting an order on Alpaca makes it disappear here
        on the next refresh."""
        self._ensure_connected()
        if not hasattr(self.broker, "get_recent_orders"):
            return []
        hidden = {OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.REJECTED}
        out = []
        for o in self.broker.get_recent_orders(limit):
            if not include_inactive and o.status in hidden:
                continue
            out.append({
                "symbol": o.symbol,
                "side": o.side.value,
                "type": o.order_type.value,
                "quantity": round(o.quantity, 4),
                "filled_quantity": round(o.filled_quantity, 4),
                "avg_fill_price": round(o.avg_fill_price, 2),
                "status": o.status.value,
                "time": o.updated_at.isoformat() if o.updated_at else "",
            })
        return out

    def trades(self, limit: int = 50) -> list[dict]:
        """Recent *filled* orders presented as executed trades."""
        return [o for o in self.orders(limit) if o["status"] == "filled"]

    def equity_curve(self) -> list[dict]:
        self._ensure_connected()
        if hasattr(self.broker, "get_portfolio_history"):
            try:
                return self.broker.get_portfolio_history()
            except Exception:  # noqa: BLE001
                logger.exception("portfolio history failed")
        return []

    def clock(self) -> dict:
        self._ensure_connected()
        if hasattr(self.broker, "get_clock"):
            try:
                c = self.broker.get_clock()
                return {
                    "is_open": bool(c.get("is_open", False)),
                    "next_open": c.get("next_open", ""),
                    "next_close": c.get("next_close", ""),
                    "timestamp": c.get("timestamp", ""),
                }
            except Exception:  # noqa: BLE001
                pass
        return {"is_open": None}

    # --- analytics (all share one cached batch fetch; cheap to call) -----
    def watchlist(self) -> list[dict]:
        """What the bot 'sees' now: current signal + key indicators per symbol."""
        return self._cached("watchlist", 120, self._compute_watchlist)

    def _compute_watchlist(self) -> list[dict]:
        strategy = StrategyRegistry.create(self.strategy_name)
        positions = self._positions_map()
        bars = self._all_bars()
        rows = []
        for symbol in self.symbols:
            try:
                df = bars.get(symbol)
                if df is None or len(df) < getattr(strategy, "warmup", 50):
                    continue
                df = df.copy()
                df.attrs["symbol"] = symbol
                last = float(df["close"].iloc[-1])
                prev = float(df["close"].iloc[-2]) if len(df) > 1 else last
                ctx = StrategyContext(positions=positions)
                signals = strategy.generate_signals(df, ctx)
                signal = signals[0].type.value if signals else SignalType.HOLD.value
                cur_rsi = float(rsi(df["close"]).iloc[-1])
                trend = str(detect_trend(df["close"]).iloc[-1])
                held = symbol in positions and abs(positions[symbol].quantity) > 1e-9
                rows.append({
                    "symbol": symbol,
                    "last_price": round(last, 2),
                    "change_pct": round(last / prev - 1, 4) if prev else 0.0,
                    "signal": signal,
                    "rsi": round(cur_rsi, 1),
                    "trend": trend,
                    "held": held,
                    "position_qty": round(positions[symbol].quantity, 4) if held else 0,
                })
            except Exception:  # noqa: BLE001
                logger.exception("watchlist failed for %s", symbol)
        return rows

    def strategies(self) -> list[dict]:
        a = self.account()
        return [{
            "name": self.strategy_name, "status": "live",
            "symbols": len(self.symbols), "day_pnl": a["day_pnl"],
            "open_positions": a["num_positions"],
        }]

    def risk(self) -> dict:
        a = self.account()
        equity = a["equity"] or 1.0
        return {
            "max_daily_loss_pct": self.risk_limits.max_daily_loss_pct,
            "max_drawdown_pct": self.risk_limits.max_drawdown_pct,
            "max_position_pct": self.risk_limits.max_position_pct,
            "day_pnl_pct": a["day_pnl_pct"],
            "gross_exposure": round(a["positions_value"] / equity, 4),
            "buying_power": a["buying_power"],
        }

    def predictions(self) -> list[dict]:
        # Model training is CPU-heavy -> cache for 30 min.
        return self._cached("predictions", 1800, self._compute_predictions)

    def _compute_predictions(self) -> list[dict]:
        from ..ml import FeatureEngineer, RandomForestModel
        fe = FeatureEngineer()
        bars = self._all_bars()
        out = []
        for symbol in self.symbols[:6]:
            try:
                df = bars.get(symbol)
                if df is None:
                    continue
                X, y = fe.build_dataset(df, horizon=5)
                if len(X) < 60:
                    continue
                model = RandomForestModel(n_estimators=100).fit(X.iloc[:-1], y.iloc[:-1])
                proba = model.predict_proba(X.iloc[[-1]])[0]
                up = float(proba[1]) if len(proba) > 1 else float(proba[0])
                out.append({"symbol": symbol,
                            "signal": "buy" if up > 0.5 else "sell",
                            "probability": round(up, 3), "model": "RandomForest"})
            except Exception:  # noqa: BLE001
                logger.exception("prediction failed for %s", symbol)
        return out

    def scanner(self, top_n: int = 15) -> list[dict]:
        rows = self._cached("scanner", 120, self._compute_scanner)
        return rows[:top_n]

    def _compute_scanner(self) -> list[dict]:
        scanner = MarketScanner(self.provider)
        bars = self._all_bars()
        results = []
        for symbol, df in bars.items():
            try:
                res = scanner._score_symbol(symbol, df)  # reuse scoring, no refetch
                if res is not None:
                    results.append(res)
            except Exception:  # noqa: BLE001
                logger.exception("scan failed for %s", symbol)
        results.sort(key=lambda r: r.score, reverse=True)
        return [{"symbol": r.symbol, "score": r.score, "reason": r.reason,
                 "price": r.price, "change_pct": r.change_pct, "metrics": r.metrics}
                for r in results]
