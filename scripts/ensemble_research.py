"""RESEARCH-ONLY backtest of the multi-strategy ensemble design.

NOT wired into the live bot. A faithful-as-practical, long-only DAILY version of
the design's testable core: trend + cross-sectional momentum + mean-reversion
(range regime only) + vol-breakout, combined under a regime gate, inverse-vol
weighting and vol-targeted exposure, with realistic costs. Tested across several
market regimes and ETF baskets.

Simplifications (flagged honestly): long-only (no shorts/futures), no L2 order
flow, no tail hedge, 5-day rebalance, simple vol-target via market-vol scaling.
"""
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
import sys
sys.path.insert(0, ".")
from quanttrade.data import create_data_provider
from quanttrade.portfolio import analytics

ETFS = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLU", "GLD", "TLT", "HYG"]
COST = 0.0003  # 3 bps per unit turnover (commission + half-spread + slippage)


def rsi(series, n):
    d = series.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def build_signals(close):
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    vol20 = close.pct_change().rolling(20).std() * np.sqrt(252)
    r = rsi(close, 2)
    mom = close.shift(21) / close.shift(147) - 1.0          # 6m return, skip last month
    # Bollinger width + breakout
    mid = close.rolling(20).mean(); sd = close.rolling(20).std()
    width = (2 * sd) / mid
    compressed = width < width.rolling(60).quantile(0.25)
    breakout = close > (mid + 2 * sd)

    trend = ((close > sma200) & (close > sma50)).astype(float)
    meanrev = ((r < 10) & (close > sma200)).astype(float)
    volbrk = (compressed.shift(1).fillna(False) & breakout).astype(float)
    # cross-sectional momentum: top third by 6m return each day
    rank = mom.rank(axis=1, pct=True)
    xmom = (rank >= 0.66).astype(float)
    return dict(trend=trend, xmom=xmom, meanrev=meanrev, volbrk=volbrk, vol20=vol20, sma200=sma200)


def adx_proxy(close, n=14):
    # simple trend-strength proxy: |200d slope| normalized, on SPY
    slope = close.diff(20) / close
    return slope.abs().rolling(n).mean() * 100


def backtest(prices, sig, weights, start, end, market="SPY"):
    spy = prices[market]
    spy_trend = spy > sig["sma200"][market]
    spy_strength = adx_proxy(spy) > 1.0
    regime_trend = (spy_trend & spy_strength)             # else "range"
    spy_vol = spy.pct_change().rolling(20).std() * np.sqrt(252)
    exposure = (0.11 / spy_vol).clip(0.3, 1.0)             # vol-targeted gross

    wt = pd.Series(np.where(regime_trend, weights["trend"]["t"], weights["range"]["t"]), index=prices.index)
    wx = pd.Series(np.where(regime_trend, weights["trend"]["x"], weights["range"]["x"]), index=prices.index)
    wm = pd.Series(np.where(regime_trend, weights["trend"]["m"], weights["range"]["m"]), index=prices.index)
    wv = pd.Series(np.where(regime_trend, weights["trend"]["v"], weights["range"]["v"]), index=prices.index)

    blended = (sig["trend"].mul(wt, axis=0) + sig["xmom"].mul(wx, axis=0)
               + sig["meanrev"].mul(wm, axis=0) + sig["volbrk"].mul(wv, axis=0))
    inv_vol = blended / sig["vol20"].replace(0, np.nan)
    inv_vol = inv_vol.fillna(0.0).clip(lower=0)
    row = inv_vol.sum(axis=1).replace(0, np.nan)
    target = inv_vol.div(row, axis=0).fillna(0.0).mul(exposure, axis=0)

    # rebalance every 5 trading days
    reb = (np.arange(len(target)) % 5 == 0)
    held = target.where(pd.Series(reb, index=target.index), np.nan).ffill().fillna(0.0)

    asset_ret = prices.pct_change().fillna(0.0)
    gross = (held.shift(1) * asset_ret).sum(axis=1)
    turnover = (held - held.shift(1)).abs().sum(axis=1)
    net = gross - turnover * COST
    eq = (1 + net).cumprod() * 100_000
    eq = eq.loc[str(start):str(end)]
    return eq / eq.iloc[0] * 100_000


def metrics(eq):
    r = analytics.analyze(eq)
    return f"{r.total_return:+7.1%} {r.cagr:+6.1%} {r.sharpe:6.2f} {r.sortino:6.2f} {r.max_drawdown:7.1%} {r.calmar:6.2f}"


print("Downloading ETF data ...")
prov = create_data_provider("yfinance")
raw = prov.get_multiple(ETFS, datetime(2017, 1, 1), datetime(2024, 1, 1))
prices = pd.DataFrame({s: d["close"] for s, d in raw.items() if d is not None and len(d) > 400}).dropna()
print("assets:", list(prices.columns), "| bars:", len(prices), "\n")
sig = build_signals(prices)

ENSEMBLE = {"trend": dict(t=0.4, x=0.4, m=0.0, v=0.2), "range": dict(t=0.2, x=0.2, m=0.4, v=0.2)}
TREND_ONLY = {"trend": dict(t=1, x=0, m=0, v=0), "range": dict(t=1, x=0, m=0, v=0)}
MEANREV_ONLY = {"trend": dict(t=0, x=0, m=1, v=0), "range": dict(t=0, x=0, m=1, v=0)}

scenarios = {
    "2020 COVID crash+rebound": (2020, 2020),
    "2021 calm bull": (2021, 2021),
    "2022 bear market": (2022, 2022),
    "2023 AI bull": (2023, 2023),
    "2018-2023 full (multi-regime)": (2018, 2023),
}

hdr = f"{'variant':14s} {'return':>8s} {'cagr':>6s} {'sharpe':>6s} {'sortino':>6s} {'maxDD':>7s} {'calmar':>6s}"
for label, (a, b) in scenarios.items():
    print(f"=== {label} ===")
    print(hdr)
    print(f"{'ENSEMBLE':14s} {metrics(backtest(prices, sig, ENSEMBLE, a, b))}")
    print(f"{'trend-only':14s} {metrics(backtest(prices, sig, TREND_ONLY, a, b))}")
    print(f"{'meanrev-only':14s} {metrics(backtest(prices, sig, MEANREV_ONLY, a, b))}")
    spy_eq = (prices["SPY"].loc[str(a):str(b)] / prices["SPY"].loc[str(a):str(b)].iloc[0] * 100_000)
    print(f"{'SPY buy&hold':14s} {metrics(spy_eq)}")
    print()
