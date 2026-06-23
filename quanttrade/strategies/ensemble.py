"""Regime-aware multi-sleeve ensemble allocator (portfolio-level).

This is NOT a per-symbol ``Strategy`` -- it looks at the whole basket at once and
returns target portfolio weights. It implements the testable daily core of the
multi-strategy design: trend + cross-sectional momentum + mean-reversion
(range-regime only) + vol-breakout, combined under a regime gate, inverse-vol
weighting and vol-targeted exposure. Long-only.

Driven live by :class:`quanttrade.execution.portfolio_engine.PortfolioEngine`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Regime weights: (trend, x-momentum, mean-reversion, vol-breakout)
_WEIGHTS = {
    "trend": dict(t=0.40, x=0.40, m=0.00, v=0.20),
    "range": dict(t=0.20, x=0.20, m=0.40, v=0.20),
}


def _rsi(series: pd.Series, n: int) -> pd.Series:
    d = series.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


class EnsembleAllocator:
    """Computes target portfolio weights from a basket of OHLCV bars."""

    name = "ensemble"
    warmup = 210
    vol_target = 0.11

    def __init__(self, market: str = "SPY") -> None:
        self.market = market

    def _latest(self, bars: dict[str, pd.DataFrame]):
        # Only include symbols that actually have enough history, so one bad /
        # short / missing ticker can't wipe the whole basket via row-wise dropna.
        cols = {s: d["close"] for s, d in bars.items()
                if d is not None and d["close"].notna().sum() >= self.warmup}
        if not cols:
            return pd.DataFrame()
        closes = pd.DataFrame(cols)
        closes = closes.dropna(axis=1, thresh=self.warmup)  # drop thin columns
        closes = closes.ffill().dropna()                    # fill gaps, drop leading NaN
        return closes

    def target_weights(self, bars: dict[str, pd.DataFrame]) -> dict[str, float]:
        rows = self.detail(bars)
        return {r["symbol"]: r["weight"] for r in rows if r["weight"] > 0}

    def detail(self, bars: dict[str, pd.DataFrame]) -> list[dict]:
        """Per-symbol target weight + indicators (also used by the dashboard)."""
        closes = self._latest(bars)
        if closes.empty or len(closes) < self.warmup:
            return []
        sma50 = closes.rolling(50).mean()
        sma200 = closes.rolling(200).mean()
        vol20 = closes.pct_change().rolling(20).std() * np.sqrt(252)
        rsi2 = closes.apply(lambda c: _rsi(c, 2))
        mom = closes.shift(21) / closes.shift(147) - 1.0
        mid = closes.rolling(20).mean(); sd = closes.rolling(20).std()
        width = (2 * sd) / mid
        compressed = width < width.rolling(60).quantile(0.25)
        breakout = closes > (mid + 2 * sd)

        last = closes.index[-1]
        trend = ((closes > sma200) & (closes > sma50)).loc[last]
        meanrev = ((rsi2 < 10) & (closes > sma200)).loc[last]
        volbrk = (compressed.shift(1).fillna(False) & breakout).loc[last]
        rank = mom.rank(axis=1, pct=True).loc[last]
        xmom = (rank >= 0.66)

        # market regime
        mkt = self.market if self.market in closes else closes.columns[0]
        m = closes[mkt]
        regime_trend = bool(m.iloc[-1] > sma200[mkt].iloc[-1]
                            and (m.diff(20).iloc[-1] / m.iloc[-1]) > 0)
        w = _WEIGHTS["trend"] if regime_trend else _WEIGHTS["range"]
        mkt_vol = float(vol20[mkt].iloc[-1]) or self.vol_target
        exposure = float(np.clip(self.vol_target / mkt_vol, 0.3, 1.0))

        blended = {}
        for s in closes.columns:
            b = (w["t"] * float(trend[s]) + w["x"] * float(xmom[s])
                 + w["m"] * float(meanrev[s]) + w["v"] * float(volbrk[s]))
            v = float(vol20[s].iloc[-1] if hasattr(vol20[s], "iloc") else vol20[s])
            blended[s] = (b / v) if (b > 0 and v > 0) else 0.0
        total = sum(blended.values())

        rows = []
        for s in closes.columns:
            weight = (blended[s] / total * exposure) if total > 0 else 0.0
            c = closes[s]
            rows.append({
                "symbol": s,
                "last_price": round(float(c.iloc[-1]), 2),
                "change_pct": round(float(c.iloc[-1] / c.iloc[-2] - 1), 4),
                "weight": round(weight, 4),
                "signal": "buy" if weight > 0 else "hold",
                "rsi": round(float(_rsi(c, 14).iloc[-1]), 1),
                "trend": "uptrend" if bool(trend[s]) else "—",
                "regime": "trend" if regime_trend else "range",
            })
        rows.sort(key=lambda r: r["weight"], reverse=True)
        return rows
