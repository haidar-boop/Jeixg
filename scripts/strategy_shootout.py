"""Out-of-sample strategy shootout on REAL data (not committed to the bot)."""
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from quanttrade.backtest import BacktestEngine
from quanttrade.data import create_data_provider
from quanttrade.risk import FixedFractionSizer, RiskLimits, RiskManager
import quanttrade.strategies  # noqa: F401  registers strategies
from quanttrade.strategies import StrategyRegistry

SYMBOLS = ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "JPM", "WMT", "XOM", "QQQ", "SPY"]
STRATS = ["trend_momentum", "trend_macd", "trend_pullback", "ma_crossover",
          "momentum", "breakout", "rsi_reversion", "bollinger_reversion"]

print("Downloading real data for", len(SYMBOLS), "symbols ...")
prov = create_data_provider("yfinance")
allbars = prov.get_multiple(SYMBOLS, datetime(2015, 1, 1), datetime(2024, 1, 1))
allbars = {s: d for s, d in allbars.items() if d is not None and len(d) > 300}
print("got", len(allbars), "symbols with data\n")


def slice_period(start, end):
    out = {}
    for s, d in allbars.items():
        sub = d.loc[str(start):str(end)]
        if len(sub) > 250:
            out[s] = sub
    return out


def run(strat_name, data):
    eng = BacktestEngine(
        StrategyRegistry.create(strat_name),
        starting_cash=100_000, commission_per_share=0.005, slippage_bps=1.0,
        sizer=FixedFractionSizer(0.10),
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.5,
                                            max_gross_exposure_pct=3.0,
                                            max_daily_loss_pct=0.95,
                                            max_drawdown_pct=0.95)),
    )
    return eng.run(data).summary()


def bh(data):  # buy-and-hold benchmark (equal weight)
    import numpy as np
    rets = []
    for d in data.values():
        rets.append(d["close"].iloc[-1] / d["close"].iloc[0] - 1)
    return float(np.mean(rets))


periods = {"IN-SAMPLE 2018-2020": (2018, 2020), "OUT-SAMPLE 2021-2023": (2021, 2023)}
results = {}
for label, (a, b) in periods.items():
    data = slice_period(a, b)
    print(f"=== {label}  ({len(data)} symbols) ===")
    print(f"{'strategy':18s} {'return':>8s} {'sharpe':>7s} {'maxDD':>7s} {'trades':>7s} {'win%':>6s}")
    rows = []
    for st in STRATS:
        try:
            s = run(st, data)
            rows.append((st, s))
        except Exception as e:
            print(f"  {st}: FAILED {e}")
    rows.sort(key=lambda r: r[1]["total_return"], reverse=True)
    for st, s in rows:
        print(f"{st:18s} {s['total_return']:+7.1%} {s['sharpe']:7.2f} "
              f"{s['max_drawdown']:7.1%} {s['num_trades']:7d} {s['win_rate']:6.0%}")
    print(f"{'buy & hold (eq wt)':18s} {bh(data):+7.1%}")
    results[label] = {st: s for st, s in rows}
    print()

print("=== RANKED BY OUT-OF-SAMPLE RETURN (the honest test) ===")
oos = results["OUT-SAMPLE 2021-2023"]
for st in sorted(oos, key=lambda x: oos[x]["total_return"], reverse=True):
    s = oos[st]
    print(f"{st:18s} OOS return {s['total_return']:+7.1%}  sharpe {s['sharpe']:.2f}  maxDD {s['max_drawdown']:+.1%}")
