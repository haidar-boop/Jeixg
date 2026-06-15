"""Market scanner.

Ranks a universe of symbols against a set of composable filters/criteria
(momentum, RSI extremes, volume spikes, breakouts, volatility). Returns a scored,
sorted list that the dashboard and strategies can consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from ..core.enums import BarInterval
from ..core.logging_config import get_logger
from ..data.base import MarketDataProvider
from ..indicators import atr, rsi

logger = get_logger(__name__)


@dataclass
class ScanResult:
    symbol: str
    score: float
    price: float
    change_pct: float
    reason: str
    metrics: dict = field(default_factory=dict)


@dataclass
class ScanCriteria:
    min_price: float = 1.0
    max_price: float = 1e9
    min_avg_volume: float = 0.0
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    momentum_lookback: int = 20
    breakout_window: int = 20


class MarketScanner:
    """Scans a universe and scores each symbol by configurable signals."""

    def __init__(self, data_provider: MarketDataProvider,
                 criteria: ScanCriteria | None = None) -> None:
        self.data = data_provider
        self.criteria = criteria or ScanCriteria()

    def scan(self, universe: list[str], *, lookback_days: int = 120,
             top_n: int | None = None) -> list[ScanResult]:
        end = datetime.utcnow()
        start = end - pd.Timedelta(days=lookback_days * 2)
        results: list[ScanResult] = []
        for symbol in universe:
            try:
                bars = self.data.get_historical_bars(symbol, start, end, BarInterval.DAY_1)
            except Exception:  # noqa: BLE001
                logger.warning("Scanner: no data for %s", symbol)
                continue
            res = self._score_symbol(symbol, bars)
            if res is not None:
                results.append(res)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_n] if top_n else results

    def _score_symbol(self, symbol: str, bars: pd.DataFrame) -> ScanResult | None:
        c = self.criteria
        if len(bars) < max(c.momentum_lookback, c.breakout_window) + 2:
            return None
        close = bars["close"]
        price = float(close.iloc[-1])
        avg_vol = float(bars["volume"].tail(20).mean())
        if not (c.min_price <= price <= c.max_price) or avg_vol < c.min_avg_volume:
            return None

        change_pct = float(close.iloc[-1] / close.iloc[-2] - 1.0)
        momentum = float(close.iloc[-1] / close.iloc[-c.momentum_lookback] - 1.0)
        cur_rsi = float(rsi(close).iloc[-1])
        atr_pct = float(atr(bars["high"], bars["low"], close).iloc[-1]) / price
        vol_spike = float(bars["volume"].iloc[-1] / max(avg_vol, 1e-9))
        prior_high = float(bars["high"].iloc[-c.breakout_window - 1:-1].max())
        breakout = price > prior_high

        score = 0.0
        reasons: list[str] = []
        score += momentum * 100
        if momentum > 0.05:
            reasons.append(f"momentum {momentum:.1%}")
        if cur_rsi < c.rsi_oversold:
            score += (c.rsi_oversold - cur_rsi)
            reasons.append(f"oversold RSI {cur_rsi:.0f}")
        elif cur_rsi > c.rsi_overbought:
            reasons.append(f"overbought RSI {cur_rsi:.0f}")
        if vol_spike > 1.5:
            score += (vol_spike - 1) * 10
            reasons.append(f"volume {vol_spike:.1f}x")
        if breakout:
            score += 25
            reasons.append(f"breakout > {prior_high:.2f}")

        return ScanResult(
            symbol=symbol,
            score=round(score, 3),
            price=round(price, 4),
            change_pct=round(change_pct, 4),
            reason=", ".join(reasons) or "neutral",
            metrics={"rsi": round(cur_rsi, 1), "momentum": round(momentum, 4),
                     "atr_pct": round(atr_pct, 4), "vol_spike": round(vol_spike, 2)},
        )
