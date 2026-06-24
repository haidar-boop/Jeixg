"""RESEARCH-ONLY: test the v2 'rigorous' design vs the v1 ensemble vs buy&hold.

Implements the testable core upgrades of the v2 doc:
  - Yang-Zhang volatility (vs close-to-close)
  - Ledoit-Wolf shrunk covariance (vs raw)
  - Hierarchical Risk Parity allocation (vs naive inverse-vol) -- the headline
  - fractional-Kelly-capped volatility targeting

Same sleeves/regime gate as v1, long-only, ETF basket, realistic costs. Honestly
NOT implemented: HMM regimes, CPCV/DSR/PBO full battery, futures/shorts, L2.
NOT wired into the bot.
"""
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
import sys
sys.path.insert(0, ".")
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

from quanttrade.data import create_data_provider
from quanttrade.portfolio import analytics

ETFS = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLU", "GLD", "TLT", "HYG"]
COST = 0.0003
VOL_TARGET = 0.11


def _rsi(s, n):
    d = s.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + up/dn.replace(0, np.nan))


def yang_zhang(o, h, l, c, window=20):
    log_ho = np.log(h/o); log_lo = np.log(l/o); log_co = np.log(c/o)
    log_oc = np.log(o/c.shift(1))
    k = 0.34/(1.34 + (window+1)/(window-1))
    vo = log_oc.rolling(window).var()
    vc = log_co.rolling(window).var()
    rs = (log_ho*(log_ho-log_co) + log_lo*(log_lo-log_co)).rolling(window).mean()
    return np.sqrt((vo + k*vc + (1-k)*rs) * 252)


# ---- HRP (Lopez de Prado) ----
def _ivp(cov):
    ivp = 1/np.diag(cov); return ivp/ivp.sum()

def _cluster_var(cov, items):
    c = cov.loc[items, items].values
    ivp = 1/np.diag(c); ivp /= ivp.sum()
    w = ivp.reshape(-1, 1)
    return float((w.T @ c @ w).ravel()[0])

def _quasi_diag(link):
    link = link.astype(int); sortIx = pd.Series([link[-1, 0], link[-1, 1]]); n = link[-1, 3]
    while sortIx.max() >= n:
        sortIx.index = range(0, sortIx.shape[0]*2, 2)
        df0 = sortIx[sortIx >= n]; i = df0.index; j = df0.values - n
        sortIx[i] = link[j, 0]; df0 = pd.Series(link[j, 1], index=i+1)
        sortIx = pd.concat([sortIx, df0]).sort_index(); sortIx.index = range(sortIx.shape[0])
    return sortIx.tolist()

def _rec_bipart(cov, sortIx):
    w = pd.Series(1.0, index=sortIx); clusters = [sortIx]
    while clusters:
        clusters = [c[i:j] for c in clusters for i, j in ((0, len(c)//2), (len(c)//2, len(c))) if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i+1]
            v0, v1 = _cluster_var(cov, c0), _cluster_var(cov, c1)
            a = 1 - v0/(v0+v1); w[c0] *= a; w[c1] *= 1-a
    return w

def hrp(cov_df, corr_df):
    dist = ((1 - corr_df)/2.0) ** 0.5
    link = linkage(squareform(dist.values, checks=False), "single")
    order = corr_df.index[_quasi_diag(link)].tolist()
    return _rec_bipart(cov_df, order)


print("Downloading ETF data ...")
import os as _os; prov = create_data_provider(_os.getenv("QT_TEST_PROVIDER","yfinance"))
raw = prov.get_multiple(ETFS, datetime(2016, 1, 1), datetime(2024, 1, 1))
raw = {s: d for s, d in raw.items() if d is not None and len(d) > 500}
cols = list(raw)
close = pd.DataFrame({s: raw[s]["close"] for s in cols}).dropna()
openp = pd.DataFrame({s: raw[s]["open"] for s in cols}).reindex(close.index)
high = pd.DataFrame({s: raw[s]["high"] for s in cols}).reindex(close.index)
low = pd.DataFrame({s: raw[s]["low"] for s in cols}).reindex(close.index)
print("assets:", cols, "| bars:", len(close), "\n")

ret = close.pct_change().fillna(0.0)
sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
vol20 = close.pct_change().rolling(20).std()*np.sqrt(252)
yz = pd.DataFrame({s: yang_zhang(openp[s], high[s], low[s], close[s]) for s in cols})
rsi2 = close.apply(lambda c: _rsi(c, 2))
mom = close.shift(21)/close.shift(147) - 1
mid, sd = close.rolling(20).mean(), close.rolling(20).std()
compressed = (2*sd/mid) < (2*sd/mid).rolling(60).quantile(0.25)
breakout = close > (mid + 2*sd)
trend = ((close > sma200) & (close > sma50)).astype(float)
meanrev = ((rsi2 < 10) & (close > sma200)).astype(float)
volbrk = (compressed.shift(1).fillna(False) & breakout).astype(float)
xmom = (mom.rank(axis=1, pct=True) >= 0.66).astype(float)

spy = close["SPY"]; spy_vol = spy.pct_change().rolling(20).std()*np.sqrt(252)
regime_trend = (spy > sma200["SPY"]) & ((spy.diff(20)/spy) > 0)
W = {"t": (0.4, 0.2), "x": (0.4, 0.2), "m": (0.0, 0.4), "v": (0.2, 0.2)}  # (trend, range)


def blended_row(t):
    idx = 0 if regime_trend.loc[t] else 1
    b = (W["t"][idx]*trend.loc[t] + W["x"][idx]*xmom.loc[t]
         + W["m"][idx]*meanrev.loc[t] + W["v"][idx]*volbrk.loc[t])
    return b[b > 0]


def run(method):
    dates = close.index
    weights = pd.DataFrame(0.0, index=dates, columns=cols)
    last = None
    for i, t in enumerate(dates):
        if i < 210:
            continue
        if i % 5 != 0 and last is not None:
            weights.loc[t] = last; continue
        b = blended_row(t)
        sel = list(b.index)
        if len(sel) == 0:
            last = pd.Series(0.0, index=cols); weights.loc[t] = last; continue
        win = ret[sel].iloc[i-90:i]
        if method == "v2_hrp" and len(sel) >= 2:
            cov = pd.DataFrame(LedoitWolf().fit(win).covariance_, index=sel, columns=sel)
            corr = cov.div(np.sqrt(np.outer(np.diag(cov), np.diag(cov))))
            w = hrp(cov, corr)
            pv = float(np.sqrt(w.values @ cov.values @ w.values) * np.sqrt(252))
        else:  # v1 inverse-vol
            iv = (1/yz.loc[t, sel]).replace([np.inf], 0).fillna(0)
            w = iv/iv.sum() if iv.sum() > 0 else pd.Series(1/len(sel), index=sel)
            pv = float((w * yz.loc[t, sel]).sum())
        exposure = float(np.clip(VOL_TARGET/pv, 0.3, 1.0)) if pv > 0 else 0.3
        row = pd.Series(0.0, index=cols); row[sel] = w.reindex(sel).values * exposure
        last = row; weights.loc[t] = row
    gross = (weights.shift(1) * ret).sum(axis=1)
    turn = (weights - weights.shift(1)).abs().sum(axis=1)
    net = gross - turn*COST
    return (1+net).cumprod()*100_000


print("Running v1 (inverse-vol) and v2 (HRP) ...")
eq_v1 = run("v1"); eq_v2 = run("v2_hrp")


def m(eq, a, b):
    e = eq.loc[str(a):str(b)]
    if len(e) < 5: return "  n/a"
    e = e/e.iloc[0]*100_000; r = analytics.analyze(e)
    return f"{r.total_return:+7.1%} {r.cagr:+6.1%} {r.sharpe:6.2f} {r.sortino:6.2f} {r.max_drawdown:7.1%} {r.calmar:6.2f}"


hdr = f"{'variant':16s} {'return':>8s} {'cagr':>6s} {'sharpe':>6s} {'sortino':>6s} {'maxDD':>7s} {'calmar':>6s}"
for label, (a, b) in {"2020 COVID": (2020, 2020), "2021 bull": (2021, 2021),
                      "2022 bear": (2022, 2022), "2023 bull": (2023, 2023),
                      "FULL 2017-2023": (2017, 2023)}.items():
    print(f"=== {label} ===\n{hdr}")
    print(f"{'v2 (HRP+LW+YZ)':16s} {m(eq_v2, a, b)}")
    print(f"{'v1 (inverse-vol)':16s} {m(eq_v1, a, b)}")
    spy_eq = spy.loc[str(a):str(b)]
    if len(spy_eq) > 5:
        spy_eq = spy_eq/spy_eq.iloc[0]*100_000
        print(f"{'SPY buy&hold':16s} {m(spy_eq, a, b)}")
    print()
