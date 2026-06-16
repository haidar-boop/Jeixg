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

from datetime import datetime, timedelta, timezone

from ..brokers.base import Broker
from ..core.enums import BarInterval, SignalType
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
        self._bars_cache: dict[str, tuple[datetime, object]] = {}

    # --- helpers --------------------------------------------------------
    def _ensure_connected(self) -> None:
        if not self.broker.is_connected:
            self.broker.connect()

    def _bars(self, symbol: str, days: int = 300):
        """Cached daily bars per symbol (5-min freshness)."""
        now = datetime.now(timezone.utc)
        hit = self._bars_cache.get(symbol)
        if hit and (now - hit[0]).total_seconds() < 300:
            return hit[1]
        df = self.provider.get_historical_bars(
            symbol, now - timedelta(days=days * 2), now, BarInterval.DAY_1)
        self._bars_cache[symbol] = (now, df)
        return df

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

    def orders(self, limit: int = 50) -> list[dict]:
        self._ensure_connected()
        if not hasattr(self.broker, "get_recent_orders"):
            return []
        out = []
        for o in self.broker.get_recent_orders(limit):
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

    # --- analytics ------------------------------------------------------
    def watchlist(self) -> list[dict]:
        """What the bot 'sees' now: current signal + key indicators per symbol."""
        strategy = StrategyRegistry.create(self.strategy_name)
        positions = self._positions_map()
        rows = []
        for symbol in self.symbols:
            try:
                df = self._bars(symbol)
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
        from ..ml import FeatureEngineer, RandomForestModel
        fe = FeatureEngineer()
        out = []
        for symbol in self.symbols[:8]:
            try:
                df = self._bars(symbol)
                X, y = fe.build_dataset(df, horizon=5)
                if len(X) < 60:
                    continue
                model = RandomForestModel(n_estimators=120).fit(X.iloc[:-1], y.iloc[:-1])
                proba = model.predict_proba(X.iloc[[-1]])[0]
                up = float(proba[1]) if len(proba) > 1 else float(proba[0])
                out.append({"symbol": symbol,
                            "signal": "buy" if up > 0.5 else "sell",
                            "probability": round(up, 3), "model": "RandomForest"})
            except Exception:  # noqa: BLE001
                logger.exception("prediction failed for %s", symbol)
        return out

    def scanner(self, top_n: int = 15) -> list[dict]:
        results = MarketScanner(self.provider).scan(self.symbols, top_n=top_n)
        return [{"symbol": r.symbol, "score": r.score, "reason": r.reason,
                 "price": r.price, "change_pct": r.change_pct, "metrics": r.metrics}
                for r in results]
