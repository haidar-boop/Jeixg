"""RESEARCH-ONLY: how good would the framework's SCREENING have to be to beat BTC?

The base simulation (crypto_framework_sim.py) showed the framework's risk model
works (low ruin) but still trails buy & hold BTC -- UNDER THE BASELINE 70% token
death rate. The whole point of the framework's gates/fraud-detection is to lower
that death rate (screen out the rugs) and tilt toward survivors.

This asks the open question with a number: how much would the screening have to
(a) cut the death rate and/or (b) improve the survivors, for the framework to
actually beat just holding Bitcoin?

Run: .venv/bin/python scripts/crypto_framework_sensitivity.py
"""
import numpy as np

rng = np.random.default_rng(11)
N = 60_000

SURV_MU, SURV_SIGMA = np.log(0.8), 1.2       # baseline survivor multiplier
BTC_MU, BTC_SIGMA = np.log(1.3), 0.55        # BTC/ETH core per cycle


def core(n):
    return rng.lognormal(BTC_MU, BTC_SIGMA, n)


def framework(n, death_rate, surv_uplift=1.0):
    """60% BTC/ETH core + 40% across 20 satellites @ 2%, with a given death rate.
    surv_uplift multiplies survivor outcomes (screening picks better survivors)."""
    out = 0.60 * core(n)
    sat_book = np.zeros(n)
    for _ in range(20):
        alive = rng.random(n) > death_rate
        m = np.zeros(n)
        m[alive] = rng.lognormal(SURV_MU, SURV_SIGMA, alive.sum()) * surv_uplift
        sat_book += 0.02 * m
    return out + sat_book


def summ(o):
    return o.mean(), np.median(o), np.mean(o < 0.5), np.mean(o >= 2.0)


btc = core(N)
b_mean, b_med, b_ruin, b_2x = summ(btc)
print(__doc__.split("Run:")[0])
print(f"BENCHMARK  Buy & hold BTC:  mean {b_mean:.2f}x | median {b_med:.2f}x | "
      f"P(ruin) {b_ruin:.1%} | P(2x+) {b_2x:.1%}\n")

print("LEVER 1 - screening only cuts the DEATH RATE (survivors unchanged):")
hdr = f"  {'death rate':>10s} {'mean':>7s} {'median':>7s} {'P(ruin)':>8s} {'P(2x+)':>7s}  vs BTC"
print(hdr); print("  " + "-" * (len(hdr) - 2))
crossover = None
for dr in [0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10]:
    m, md, ruin, p2 = summ(framework(N, dr))
    verdict = "BEATS BTC" if m >= b_mean else "loses"
    if m >= b_mean and crossover is None:
        crossover = dr
    print(f"  {dr:9.0%} {m:6.2f}x {md:6.2f}x {ruin:7.1%} {p2:6.1%}  {verdict}")
print(f"\n  -> screening must cut deaths to about {crossover:.0%} or lower (from 70%) "
      f"to beat BTC on average." if crossover else
      "\n  -> even at a 10% death rate, cutting deaths ALONE doesn't beat BTC.")

print("\nLEVER 2 - screening also picks BETTER survivors (death rate held at 50%):")
hdr2 = f"  {'surv uplift':>11s} {'mean':>7s} {'median':>7s} {'P(ruin)':>8s} {'P(2x+)':>7s}  vs BTC"
print(hdr2); print("  " + "-" * (len(hdr2) - 2))
for up in [1.0, 1.5, 2.0, 3.0, 5.0]:
    m, md, ruin, p2 = summ(framework(N, 0.50, surv_uplift=up))
    verdict = "BEATS BTC" if m >= b_mean else "loses"
    print(f"  {up:9.1f}x {m:6.2f}x {md:6.2f}x {ruin:7.1%} {p2:6.1%}  {verdict}")

print("\nHonest read: the bar is HIGH. The screening has to be genuinely excellent")
print("-- not 'a bit better than random' -- to overtake simply holding BTC. And we")
print("can't verify it clears that bar without real on-chain data + the dead tokens.")
