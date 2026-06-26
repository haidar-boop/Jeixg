"""RESEARCH-ONLY: test a momentum strategy on smaller / sub-$1 altcoins.

Tests the framework's entry logic (cross-sectional momentum + relative strength,
regime-gated, vol-managed -- Phase 6) on a basket of REAL lower-cap altcoins,
head-to-head vs holding Bitcoin and vs holding the basket equally.

  Strategy:  each month, in a crypto-risk-on regime (BTC above its 200-day MA),
             hold the top-N altcoins by 3-month momentum, inverse-vol weighted,
             vol-targeted. Otherwise sit in cash. Realistic crypto costs.
  Benchmarks: equal-weight buy&hold of the alt basket; buy&hold BTC.

HONESTY: this basket is SURVIVORSHIP-BIASED. It only contains alts that survived
to today -- the hundreds of small tokens that went to zero are not in any free
data feed, so real-world results would be WORSE than whatever this shows. Read
the numbers as an optimistic ceiling, not an expectation.

Run: .venv/bin/python scripts/crypto_smallcap_research.py
"""
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from quanttrade.data import create_data_provider
from quanttrade.portfolio import analytics

# Smaller / lower-priced alts with enough history on yfinance (all have traded
# sub-$1 for long stretches). BTC is the regime filter + benchmark, not traded here.
ALTS = ["DOGE-USD", "XRP-USD", "ADA-USD", "TRX-USD", "XLM-USD", "ALGO-USD",
        "HBAR-USD", "VET-USD", "FTM-USD", "GRT-USD", "MANA-USD", "SAND-USD",
        "CHZ-USD", "ENJ-USD", "BAT-USD", "IOTA-USD", "ZIL-USD", "ANKR-USD"]
BENCH = "BTC-USD"
COST = 0.005            # 0.5% per unit turnover -- crypto fees + spread are real
VOL_TARGET = 0.40       # crypto runs hot; 40% annualized target
TOP_N = 5
REBAL = 30              # days (crypto trades 7d/wk)
MOM_DAYS = 90


print("Downloading crypto data ...")
prov = create_data_provider(os.getenv("QT_TEST_PROVIDER", "yfinance"))
syms = ALTS + [BENCH]
raw = prov.get_multiple(syms, datetime(2020, 1, 1), datetime(2024, 6, 1))
raw = {s: d for s, d in raw.items() if d is not None and len(d) > 300}
if BENCH not in raw:
    print("ERROR: no BTC data; aborting."); sys.exit(1)

close = pd.DataFrame({s: raw[s]["close"] for s in raw})
# keep alts with real history; forward-fill small gaps, drop leading NaNs
alts = [s for s in ALTS if s in close.columns]
close = close[alts + [BENCH]].sort_index().ffill()
btc = close[BENCH].dropna()
alt_close = close[alts]
print(f"alts with data: {len(alts)} | bars: {len(close)} | "
      f"{close.index[0].date()} -> {close.index[-1].date()}\n")

ret = alt_close.pct_change().fillna(0.0)
mom = alt_close / alt_close.shift(MOM_DAYS) - 1.0
vol = alt_close.pct_change().rolling(30).std() * np.sqrt(365)
btc_ma = btc.rolling(200).mean()
risk_on = (btc > btc_ma)


def run_momentum():
    dates = alt_close.index
    w = pd.DataFrame(0.0, index=dates, columns=alts)
    last = None
    for i, t in enumerate(dates):
        if i < 200:
            continue
        if i % REBAL != 0 and last is not None:
            w.loc[t] = last; continue
        if not bool(risk_on.loc[t]):                 # crypto risk-off -> cash
            last = pd.Series(0.0, index=alts); w.loc[t] = last; continue
        m = mom.loc[t].dropna()
        m = m[m > 0]                                  # only positive momentum
        sel = list(m.sort_values(ascending=False).head(TOP_N).index)
        if not sel:
            last = pd.Series(0.0, index=alts); w.loc[t] = last; continue
        iv = (1.0 / vol.loc[t, sel]).replace([np.inf], 0).fillna(0)
        ww = iv / iv.sum() if iv.sum() > 0 else pd.Series(1/len(sel), index=sel)
        pv = float((ww * vol.loc[t, sel]).sum())
        expo = float(np.clip(VOL_TARGET / pv, 0.2, 1.0)) if pv > 0 else 0.2
        row = pd.Series(0.0, index=alts); row[sel] = ww.values * expo
        last = row; w.loc[t] = row
    gross = (w.shift(1) * ret).sum(axis=1)
    turn = (w - w.shift(1)).abs().sum(axis=1)
    net = gross - turn * COST
    return (1 + net).cumprod() * 100_000


def equity_from(series):
    s = series.dropna()
    return s / s.iloc[0] * 100_000


def basket_buy_hold():
    eq_each = alt_close / alt_close.iloc[0]
    return (eq_each.mean(axis=1)).dropna() * 100_000


eq_mom = run_momentum()
eq_btc = equity_from(btc)
eq_basket = basket_buy_hold()


def m(eq):
    eq = eq.dropna()
    if len(eq) < 5:
        return "  n/a"
    eq = eq / eq.iloc[0] * 100_000
    r = analytics.analyze(eq)
    return (f"{r.total_return:+8.1%} {r.cagr:+7.1%} {r.sharpe:6.2f} "
            f"{r.max_drawdown:8.1%} {r.calmar:6.2f}")


print("=== Smaller / sub-$1 altcoins (survivorship-biased; optimistic ceiling) ===")
hdr = f"{'variant':26s} {'return':>8s} {'cagr':>7s} {'sharpe':>6s} {'maxDD':>8s} {'calmar':>6s}"
print(hdr); print("-" * len(hdr))
print(f"{'Momentum rotation (alts)':26s} {m(eq_mom)}")
print(f"{'Buy&hold alt basket':26s} {m(eq_basket)}")
print(f"{'Buy&hold BTC':26s} {m(eq_btc)}")
print("\nNOTE: real results would be WORSE -- the dead coins are missing from the data.")
