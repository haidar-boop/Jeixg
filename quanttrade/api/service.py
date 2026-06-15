"""Platform service layer for the API.

Holds the live application state the dashboard reads. To make the API useful out
of the box (and testable without a broker), it can bootstrap itself from a demo
backtest on synthetic data -- producing a real equity curve, trade journal,
positions, scanner output and ML predictions.

This module has **no FastAPI dependency** so it can be unit-tested directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from ..backtest import BacktestEngine
from ..core.logging_config import get_logger
from ..data import create_data_provider
from ..ml import FeatureEngineer, RandomForestModel
from ..risk import RiskLimits, RiskManager
from ..scanner import MarketScanner
from ..strategies import MovingAverageCrossover

logger = get_logger(__name__)

DEFAULT_UNIVERSE = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "NVDA", "META", "SPY"]


class PlatformService:
    """Aggregates platform state for the dashboard/API."""

    def __init__(self, universe: list[str] | None = None, starting_cash: float = 100_000.0):
        self.universe = universe or DEFAULT_UNIVERSE
        self.starting_cash = starting_cash
        self.provider = create_data_provider("synthetic")
        self._result = None
        self._equity_curve = pd.Series(dtype=float)

    # --- bootstrap ------------------------------------------------------
    def bootstrap_demo(self) -> None:
        """Run a demo backtest so the dashboard has real numbers to show."""
        end = datetime.utcnow()
        start = end - timedelta(days=730)
        data = {s: self.provider.get_historical_bars(s, start, end) for s in self.universe[:4]}
        engine = BacktestEngine(
            MovingAverageCrossover(fast=10, slow=30),
            starting_cash=self.starting_cash,
            risk_manager=RiskManager(RiskLimits(max_position_pct=0.3,
                                                max_daily_loss_pct=0.1,
                                                max_drawdown_pct=0.5)),
        )
        self._result = engine.run(data)
        self._equity_curve = self._result.equity_curve
        logger.info("Demo bootstrap complete: %s", self._result.summary())

    # --- views consumed by the REST layer ------------------------------
    def health(self) -> dict:
        return {"status": "ok", "bootstrapped": self._result is not None,
                "universe": self.universe}

    def portfolio(self) -> dict:
        if not self._result:
            return {"equity": self.starting_cash, "cash": self.starting_cash,
                    "positions_value": 0.0, "day_pnl": 0.0, "total_pnl": 0.0}
        p = self._result.portfolio
        return {
            "equity": round(p.equity, 2),
            "cash": round(p.cash, 2),
            "positions_value": round(p.positions_value, 2),
            "day_pnl": round(p.unrealized_pnl, 2),
            "total_pnl": round(p.equity - self.starting_cash, 2),
        }

    def positions(self) -> list[dict]:
        if not self._result:
            return []
        return [{
            "symbol": pos.symbol,
            "quantity": round(pos.quantity, 4),
            "avg_price": round(pos.avg_price, 2),
            "last_price": round(pos.last_price, 2),
            "unrealized_pnl": round(pos.unrealized_pnl, 2),
            "side": pos.side.value,
        } for pos in self._result.portfolio.positions.values()]

    def trades(self, limit: int = 100) -> list[dict]:
        if not self._result:
            return []
        return [{
            "symbol": t.symbol,
            "side": t.side.value,
            "quantity": round(t.quantity, 4),
            "entry_price": round(t.entry_price, 2),
            "exit_price": round(t.exit_price, 2),
            "pnl": round(t.pnl, 2),
            "return_pct": round(t.return_pct, 4),
            "exit_time": t.exit_time.isoformat(),
            "strategy": t.strategy,
        } for t in self._result.portfolio.trades[-limit:]]

    def equity_curve(self) -> list[dict]:
        return [{"timestamp": ts.isoformat(), "equity": round(float(v), 2)}
                for ts, v in self._equity_curve.items()]

    def strategies(self) -> list[dict]:
        if not self._result:
            return []
        p = self._result.performance
        return [{
            "name": "ma_crossover",
            "status": "backtest",
            "pnl": round(self._result.portfolio.equity - self.starting_cash, 2),
            "sharpe": round(p.sharpe, 3),
            "trades": p.trades.num_trades,
            "win_rate": round(p.trades.win_rate, 3),
        }]

    def risk(self) -> dict:
        dd = self._result.performance.max_drawdown if self._result else 0.0
        gross = (self._result.portfolio.positions_value /
                 max(self._result.portfolio.equity, 1e-9)) if self._result else 0.0
        return {
            "max_daily_loss_pct": 0.03,
            "current_drawdown": round(dd, 4),
            "gross_exposure": round(gross, 4),
            "var_95": round(self._value_at_risk(), 4),
        }

    def _value_at_risk(self, conf: float = 0.95) -> float:
        if len(self._equity_curve) < 3:
            return 0.0
        rets = self._equity_curve.pct_change().dropna()
        return float(rets.quantile(1 - conf))

    def predictions(self) -> list[dict]:
        """Train a quick model per symbol and emit a directional prediction."""
        out = []
        fe = FeatureEngineer()
        end = datetime.utcnow()
        start = end - timedelta(days=600)
        for symbol in self.universe[:5]:
            try:
                df = self.provider.get_historical_bars(symbol, start, end)
                X, y = fe.build_dataset(df, horizon=5)
                if len(X) < 50:
                    continue
                model = RandomForestModel()
                model.fit(X.iloc[:-1], y.iloc[:-1])
                proba = model.predict_proba(X.iloc[[-1]])[0]
                up = float(proba[1]) if len(proba) > 1 else float(proba[0])
                out.append({
                    "symbol": symbol,
                    "signal": "buy" if up > 0.5 else "sell",
                    "probability": round(up, 3),
                    "model": "RandomForest",
                })
            except Exception:  # noqa: BLE001
                logger.exception("Prediction failed for %s", symbol)
        return out

    def scanner(self, top_n: int = 10) -> list[dict]:
        scanner = MarketScanner(self.provider)
        results = scanner.scan(self.universe, top_n=top_n)
        return [{
            "symbol": r.symbol, "score": r.score, "reason": r.reason,
            "price": r.price, "change_pct": r.change_pct, "metrics": r.metrics,
        } for r in results]
