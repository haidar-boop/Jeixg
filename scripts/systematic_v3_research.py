"""RESEARCH-ONLY: test the 'Institutional-Grade Systematic Trading System' design.

This tests the genuinely-NEW, testable pieces of the v3 design document vs. the
live v1 ensemble vs. SPY buy&hold:

  - 3-state regime model (risk-on / risk-off / crisis) via a forward-filtered
    Gaussian-mixture HMM proxy on a small feature set  -- the headline upgrade
    over v1's simple "SPY vs 200-day MA" gate.
  - Drawdown throttle: exposure_mult = max(0, 1 - DD/DD_max)  (Part 5).
  - Fractional-Kelly-capped vol targeting (Part 3).
  - Honesty stats: Deflated Sharpe Ratio + a simple PBO (Part 8).

Same sleeves / ETF basket / realistic costs as the v1 and v2 research scripts, so
the comparison is apples-to-apples. Honestly NOT implemented (need data we don't
have cleanly from free OHLCV): the carry sleeve, the value/quality sleeve, the
full Baum-Welch HMM, CPCV. The regime model here uses a GaussianMixture for the
emissions plus a sticky transition matrix, forward-filtered (no look-ahead).

NOT wired into the bot. Run it:
    .venv/bin/python scripts/systematic_v3_research.py
"""
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from scipy.stats import norm
from sklearn.mixture import GaussianMixture

from quanttrade.data import create_data_provider
from quanttrade.portfolio import analytics

ETFS = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLU", "GLD", "TLT", "HYG"]
SAFE_HAVEN = {"GLD", "TLT"}          # what we keep in the CRISIS regime
COST = 0.0003
VOL_TARGET = 0.11
DD_MAX = 0.20                         # drawdown at which the throttle hits zero
REFIT_EVERY = 63                      # refit the regime model ~quarterly
STICKY = 0.97                         # regime self-transition prob (anti-whipsaw)


def _rsi(s, n):
    d = s.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + up/dn.replace(0, np.nan))


# --------------------------------------------------------------------------
print("Downloading ETF data ...")
prov = create_data_provider(os.getenv("QT_TEST_PROVIDER", "yfinance"))
raw = prov.get_multiple(ETFS, datetime(2016, 1, 1), datetime(2024, 1, 1))
raw = {s: d for s, d in raw.items() if d is not None and len(d) > 500}
cols = list(raw)
close = pd.DataFrame({s: raw[s]["close"] for s in cols}).dropna()
print("assets:", cols, "| bars:", len(close), "\n")

ret = close.pct_change().fillna(0.0)
sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
vol20 = close.pct_change().rolling(20).std() * np.sqrt(252)
rsi2 = close.apply(lambda c: _rsi(c, 2))
mom = close.shift(21) / close.shift(147) - 1
mid, sd = close.rolling(20).mean(), close.rolling(20).std()
compressed = (2*sd/mid) < (2*sd/mid).rolling(60).quantile(0.25)
breakout = close > (mid + 2*sd)
trend = ((close > sma200) & (close > sma50)).astype(float)
meanrev = ((rsi2 < 10) & (close > sma200)).astype(float)
volbrk = (compressed.shift(1).fillna(False) & breakout).astype(float)
xmom = (mom.rank(axis=1, pct=True) >= 0.66).astype(float)

# ---- regime feature set (small, robust, Part 3) --------------------------
spy = close["SPY"]
spy_ret = spy.pct_change()
feat = pd.DataFrame({
    "vol": spy_ret.rolling(20).std() * np.sqrt(252),
    "trend": (spy / sma200["SPY"] - 1.0),
    "credit": close["HYG"].pct_change(20) if "HYG" in cols else spy_ret.rolling(20).mean(),
    "breadth": trend.mean(axis=1),
}).bfill().fillna(0.0)


def label_states(gm):
    """Order GMM components by mean vol -> 0=risk-on, 1=risk-off, 2=crisis."""
    order = np.argsort(gm.means_[:, 0])          # col 0 == vol feature
    rank = {c: r for r, c in enumerate(order)}
    return rank


def regime_path(n_states=3):
    """Forward-filtered regime per day (uses only past data)."""
    X = feat.values
    states = np.zeros(len(X), dtype=int)
    gm = None; rank = None
    trans = np.full((n_states, n_states), (1 - STICKY) / (n_states - 1))
    np.fill_diagonal(trans, STICKY)
    belief = np.full(n_states, 1.0 / n_states)
    for i in range(len(X)):
        if i >= 252 and (gm is None or i % REFIT_EVERY == 0):
            gm = GaussianMixture(n_states, covariance_type="full", random_state=0,
                                 reg_covar=1e-4).fit(X[:i])      # fit on PAST only
            rank = label_states(gm)
        if gm is None:
            states[i] = 0; continue
        # emission likelihood of today's features under each (vol-ordered) state
        logp = gm._estimate_weighted_log_prob(X[i:i+1])[0]
        emis = np.zeros(n_states)
        for comp, r in rank.items():
            emis[r] = logp[comp]
        emis = np.exp(emis - emis.max())
        belief = (belief @ trans) * emis
        belief = belief / belief.sum() if belief.sum() > 0 else np.full(n_states, 1/n_states)
        states[i] = int(np.argmax(belief))
    return pd.Series(states, index=feat.index)


# regime-conditional sleeve blend weights (trend, xmom, meanrev, volbrk)
BLEND = {
    0: (0.40, 0.40, 0.00, 0.20),   # risk-on  -> momentum/trend heavy
    1: (0.25, 0.20, 0.35, 0.20),   # risk-off -> lean defensive / mean-revert
    2: (0.00, 0.00, 0.00, 0.00),   # crisis   -> flat (safe-haven only, below)
}


def blended_row(t, state):
    wt, wx, wm, wv = BLEND[state]
    b = (wt*trend.loc[t] + wx*xmom.loc[t] + wm*meanrev.loc[t] + wv*volbrk.loc[t])
    b = b[b > 0]
    if state == 2:                                  # crisis: safe-haven only
        b = pd.Series({s: 1.0 for s in SAFE_HAVEN if s in cols})
    return b


def run(use_regime, use_dd_throttle):
    dates = close.index
    regimes = regime_path() if use_regime else None
    weights = pd.DataFrame(0.0, index=dates, columns=cols)
    last = None
    for i, t in enumerate(dates):
        if i < 252:
            continue
        if i % 5 != 0 and last is not None:
            weights.loc[t] = last; continue
        if use_regime:
            state = int(regimes.iloc[i])
        else:
            state = 0 if (spy.iloc[i] > sma200["SPY"].iloc[i]) else 1   # v1 simple gate
        b = blended_row(t, state)
        sel = list(b.index)
        if not sel:
            last = pd.Series(0.0, index=cols); weights.loc[t] = last; continue
        iv = (1 / vol20.loc[t, sel]).replace([np.inf], 0).fillna(0)     # inverse-vol (v1)
        w = iv / iv.sum() if iv.sum() > 0 else pd.Series(1/len(sel), index=sel)
        pv = float((w * vol20.loc[t, sel]).sum())
        exposure = float(np.clip(VOL_TARGET / pv, 0.3, 1.0)) if pv > 0 else 0.3
        row = pd.Series(0.0, index=cols); row[sel] = w.reindex(sel).values * exposure
        last = row; weights.loc[t] = row

    gross = (weights.shift(1) * ret).sum(axis=1)
    turn = (weights - weights.shift(1)).abs().sum(axis=1)
    net = gross - turn * COST

    if use_dd_throttle:                                # de-risk smoothly in a drawdown
        eq = (1 + net).cumprod()
        peak = eq.cummax()
        dd = (peak - eq) / peak
        mult = (1 - dd / DD_MAX).clip(lower=0.0)
        net = net * mult.shift(1).fillna(1.0)

    return (1 + net).cumprod() * 100_000


# --------------------------------------------------------------------------
def deflated_sharpe(returns, n_trials):
    """Bailey & Lopez de Prado (2014), simplified. Returns P(true Sharpe>0)."""
    r = returns.dropna()
    if len(r) < 30 or r.std() == 0:
        return 0.0
    sr = r.mean() / r.std()                            # per-period
    T = len(r)
    g3 = float(pd.Series(r).skew()); g4 = float(pd.Series(r).kurt()) + 3.0
    # expected max Sharpe under the null across n_trials (per-period units)
    e = 0.5772
    z = norm.ppf(1 - 1.0/max(n_trials, 2)) if n_trials > 1 else 0.0
    z2 = norm.ppf(1 - 1.0/(max(n_trials, 2)*np.e))
    sr0 = (1.0/np.sqrt(T)) * ((1 - e)*z + e*z2)
    denom = np.sqrt((1 - g3*sr + (g4-1)/4.0*sr**2) / (T - 1))
    if denom <= 0:
        return 0.0
    return float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(max(1e-9, 1 - g3*sr + (g4-1)/4.0*sr**2))))


print("Running v3 (HMM regime + DD throttle), v1 (simple gate), and ablations ...")
eq_v3 = run(use_regime=True,  use_dd_throttle=True)
eq_v3b = run(use_regime=True,  use_dd_throttle=False)
eq_v1 = run(use_regime=False, use_dd_throttle=False)


def m(eq, a, b):
    e = eq.loc[str(a):str(b)]
    if len(e) < 5:
        return "  n/a"
    e = e / e.iloc[0] * 100_000
    r = analytics.analyze(e)
    return f"{r.total_return:+7.1%} {r.cagr:+6.1%} {r.sharpe:6.2f} {r.sortino:6.2f} {r.max_drawdown:7.1%} {r.calmar:6.2f}"


hdr = f"{'variant':22s} {'return':>8s} {'cagr':>6s} {'sharpe':>6s} {'sortino':>6s} {'maxDD':>7s} {'calmar':>6s}"
for label, (a, b) in {"2020 COVID": (2020, 2020), "2021 bull": (2021, 2021),
                      "2022 bear": (2022, 2022), "2023 bull": (2023, 2023),
                      "FULL 2017-2023": (2017, 2023)}.items():
    print(f"=== {label} ===\n{hdr}")
    print(f"{'v3 (HMM+DDthrottle)':22s} {m(eq_v3, a, b)}")
    print(f"{'v3 (HMM, no throttle)':22s} {m(eq_v3b, a, b)}")
    print(f"{'v1 (simple gate)':22s} {m(eq_v1, a, b)}")
    spy_eq = spy.loc[str(a):str(b)]
    if len(spy_eq) > 5:
        spy_eq = spy_eq / spy_eq.iloc[0] * 100_000
        print(f"{'SPY buy&hold':22s} {m(spy_eq, a, b)}")
    print()

# ---- honesty stats on the full sample ------------------------------------
print("=== Overfitting / honesty stats (full sample) ===")
N_TRIALS = 24      # rough count of sleeve/param/regime variants tried across v1->v3
for name, eq in {"v3 (HMM+throttle)": eq_v3, "v1 (simple gate)": eq_v1}.items():
    r = eq.pct_change().dropna()
    dsr = deflated_sharpe(r, N_TRIALS)
    print(f"  {name:22s} Deflated Sharpe P(edge>0 | {N_TRIALS} trials) = {dsr:5.1%}")
print("  (PBO needs the full combinatorial CV battery -- not run here; see Part 8.)")
