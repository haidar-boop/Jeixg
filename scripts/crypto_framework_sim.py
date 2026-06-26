"""RESEARCH-ONLY: test the *testable core* of the early-stage crypto framework.

WHAT THIS CAN AND CANNOT TEST
-----------------------------
The framework's stock-PICKING edge (on-chain gates, fraud/rug detection, holder
concentration, wash-trading screens, tokenomics) CANNOT be backtested with any
free price data:
  - the assets are small-cap tokens that aren't in Yahoo/yfinance at all;
  - the signals are on-chain data we don't have (GoPlus, Nansen, Etherscan, ...);
  - an honest backtest would need the DEAD tokens (the ~70% that went to zero),
    and free data only keeps survivors -> any such backtest is a survivorship-
    biased lie, which is the exact trap the document warns against.

But the framework's CENTRAL CLAIM *is* testable, and the doc says it matters most:
  "You can't reliably pick winners. You survive the catastrophic base rate by
   sizing each position so it can go to zero (<=3%), with a big BTC/ETH core."
  (Truth 1, Truth 2, Phase 5: 'how you size matters more than what you pick'.)

So this is a Monte-Carlo simulation of the SIZING / SURVIVAL logic, driven by the
document's OWN cited base rates. It does NOT predict returns -- it tests whether
the portfolio construction does what it claims: avoid ruin while keeping upside.
All assumptions are printed so you can see exactly what drives the result.

Run: .venv/bin/python scripts/crypto_framework_sim.py
"""
import numpy as np

rng = np.random.default_rng(7)
N_TRIALS = 50_000

# ---- assumptions, straight from the framework (all disclosed) -------------
DEATH_RATE = 0.70          # Truth 1: ~70% of small-caps in bull->bear cohorts die
# Survivors (the 30%): fat-tailed multiplier over one cycle. Median survivor is a
# mild loser (~0.8x); a small tail moons. lognormal(mu, sigma):
SURV_MU, SURV_SIGMA = np.log(0.8), 1.2
# BTC/ETH "core" over the same cycle: volatile but doesn't go to zero.
BTC_MU, BTC_SIGMA = np.log(1.3), 0.55     # median ~+30%, high vol


def satellite_returns(n):
    """Multiplier for n small-cap satellites: 70% -> 0, survivors fat-tailed."""
    alive = rng.random(n) > DEATH_RATE
    mult = np.zeros(n)
    s = alive.sum()
    mult[alive] = rng.lognormal(SURV_MU, SURV_SIGMA, s)
    return mult


def core_return():
    return rng.lognormal(BTC_MU, BTC_SIGMA)


def sim_framework():
    """Barbell: 60% BTC/ETH core + 40% across 20 satellites @ 2% each (<=3% cap)."""
    core = 0.60 * core_return()
    sats = 0.02 * satellite_returns(20)
    return core + sats.sum()


def sim_concentrated():
    """The anti-pattern the doc warns against: 5 satellites @ 20% each, no core."""
    sats = 0.20 * satellite_returns(5)
    return sats.sum()


def sim_all_satellite():
    """Diversified but no core: 50 satellites @ 2% each."""
    return (0.02 * satellite_returns(50)).sum()


def sim_btc():
    """Buy & hold BTC -- the benchmark."""
    return core_return()


def stats(name, outcomes):
    o = np.asarray(outcomes)
    return {
        "name": name,
        "median": np.median(o),
        "mean": o.mean(),
        "p_ruin(<0.5x)": np.mean(o < 0.5),
        "p_loss(<1x)": np.mean(o < 1.0),
        "p_2x+": np.mean(o >= 2.0),
        "p_5x+": np.mean(o >= 5.0),
        "p5": np.percentile(o, 5),
        "p95": np.percentile(o, 95),
    }


print(__doc__.split("Run:")[0])
print("ASSUMPTIONS (from the framework's own cited numbers):")
print(f"  - small-cap death rate: {DEATH_RATE:.0%}  (Truth 1)")
print(f"  - survivor multiplier: lognormal(median {np.exp(SURV_MU):.2f}x, sigma {SURV_SIGMA})")
print(f"      -> implied: P(survivor >=5x)={np.mean(rng.lognormal(SURV_MU,SURV_SIGMA,200000)>=5):.1%}, "
      f"P(survivor >=10x)={np.mean(rng.lognormal(SURV_MU,SURV_SIGMA,200000)>=10):.1%}")
print(f"  - BTC/ETH core per cycle: lognormal(median {np.exp(BTC_MU):.2f}x, sigma {BTC_SIGMA})")
print(f"  - trials: {N_TRIALS:,}\n")

variants = {
    "Framework (barbell)": sim_framework,
    "Concentrated (5 bets)": sim_concentrated,
    "All-satellite (no core)": sim_all_satellite,
    "Buy & hold BTC": sim_btc,
}
rows = [stats(name, [fn() for _ in range(N_TRIALS)]) for name, fn in variants.items()]

hdr = (f"{'variant':24s} {'median':>7s} {'mean':>7s} {'P(ruin)':>8s} {'P(loss)':>8s} "
       f"{'P(2x+)':>7s} {'P(5x+)':>7s} {'5th':>6s} {'95th':>7s}")
print(hdr)
print("-" * len(hdr))
for r in rows:
    print(f"{r['name']:24s} {r['median']:6.2f}x {r['mean']:6.2f}x "
          f"{r['p_ruin(<0.5x)']:7.1%} {r['p_loss(<1x)']:7.1%} {r['p_2x+']:6.1%} "
          f"{r['p_5x+']:6.1%} {r['p5']:5.2f}x {r['p95']:6.2f}x")

print("\nHow to read this:")
print("  median/mean = typical vs average end value (1.00x = break even)")
print("  P(ruin) = chance you end with <50% of what you started")
print("  P(2x+/5x+) = chance you at least double / 5x")
print("  5th/95th = unlucky vs lucky outcomes (the spread)")
print("\nNOTE: this tests the SIZING/SURVIVAL logic using assumed base rates, NOT")
print("real token picks. The picking edge is untestable without on-chain data and")
print("the dead tokens. Treat as illustration of the risk model, not a prediction.")
