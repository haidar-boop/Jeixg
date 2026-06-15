"""Example: run a backtest and print the performance report.

    python examples/run_backtest.py
"""
from datetime import datetime

from quanttrade.backtest import BacktestEngine
from quanttrade.data import create_data_provider
from quanttrade.risk import FixedRiskSizer, RiskLimits, RiskManager
from quanttrade.strategies import MovingAverageCrossover


def main() -> None:
    provider = create_data_provider("synthetic")  # swap for "yfinance" with real data
    symbols = ["AAPL", "MSFT", "GOOG"]
    data = {
        s: provider.get_historical_bars(s, datetime(2019, 1, 1), datetime(2023, 1, 1))
        for s in symbols
    }

    strategy = MovingAverageCrossover(fast=20, slow=50, atr_mult=2.0)
    risk = RiskManager(RiskLimits(
        max_position_pct=0.25, max_daily_loss_pct=0.05, max_drawdown_pct=0.30,
    ))

    engine = BacktestEngine(
        strategy,
        starting_cash=100_000,
        commission_per_share=0.005,
        slippage_bps=1.0,
        sizer=FixedRiskSizer(risk_pct=0.01),
        risk_manager=risk,
    )
    result = engine.run(data)

    print("\n=== Backtest Summary ===")
    for key, value in result.summary().items():
        print(f"  {key:18s}: {value}")
    print(f"\n  trades recorded     : {len(result.portfolio.trades)}")
    print(f"  orders blocked      : {result.blocked_orders}")


if __name__ == "__main__":
    main()
