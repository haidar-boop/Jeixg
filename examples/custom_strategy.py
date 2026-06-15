"""Example: write and register a custom strategy plug-in.

Demonstrates the plug-in model -- subclass Strategy, decorate with
@register_strategy, and it becomes available by name everywhere (CLI, optimizer,
config). Run:

    python examples/custom_strategy.py
"""
from datetime import datetime

import pandas as pd

from quanttrade.backtest import BacktestEngine
from quanttrade.core.enums import SignalType
from quanttrade.data import create_data_provider
from quanttrade.indicators import rsi, sma
from quanttrade.models import Signal
from quanttrade.risk import RiskLimits, RiskManager
from quanttrade.strategies.base import Strategy, StrategyContext, register_strategy


@register_strategy("rsi_trend")
class RSITrendStrategy(Strategy):
    """Buy pullbacks (RSI dip) within an established uptrend (price > SMA200)."""

    def on_init(self) -> None:
        self.sma_period = int(self.params.get("sma_period", 200))
        self.rsi_buy = float(self.params.get("rsi_buy", 40))
        self.rsi_exit = float(self.params.get("rsi_exit", 65))
        self.warmup = self.sma_period + 2

    def generate_signals(self, data: pd.DataFrame, ctx: StrategyContext) -> list[Signal]:
        if len(data) < self.warmup:
            return []
        close = data["close"]
        price = float(close.iloc[-1])
        trend_ok = price > float(sma(close, self.sma_period).iloc[-1])
        r = float(rsi(close).iloc[-1])
        symbol = data.attrs.get("symbol", "")

        if trend_ok and r < self.rsi_buy and not ctx.has_position(symbol):
            return [Signal(symbol, SignalType.BUY, price=price,
                           stop_loss=price * 0.93, strategy=self.name)]
        if ctx.has_position(symbol) and (r > self.rsi_exit or not trend_ok):
            return [Signal(symbol, SignalType.CLOSE, price=price, strategy=self.name)]
        return []


def main() -> None:
    provider = create_data_provider("synthetic")
    data = {"AAPL": provider.get_historical_bars("AAPL", datetime(2018, 1, 1),
                                                 datetime(2023, 1, 1))}
    engine = BacktestEngine(
        RSITrendStrategy(sma_period=100),
        risk_manager=RiskManager(RiskLimits(max_position_pct=0.5,
                                            max_daily_loss_pct=0.1,
                                            max_drawdown_pct=0.5)),
    )
    print(engine.run(data).summary())


if __name__ == "__main__":
    main()
