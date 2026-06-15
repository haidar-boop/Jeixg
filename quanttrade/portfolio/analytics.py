"""Performance and risk analytics.

Computes the standard institutional metric suite from an equity curve and/or a
list of completed trades: returns, volatility, Sharpe, Sortino, Calmar, max
drawdown, alpha/beta vs a benchmark, win-rate, profit factor and expectancy.

All metrics are computed defensively (empty / constant series return 0 rather
than raising) so they are safe to call on partial backtests.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _to_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def sharpe_ratio(returns: pd.Series, risk_free: float = 0.0,
                 periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2 or returns.std(ddof=1) == 0:
        return 0.0
    excess = returns - risk_free / periods
    return float(np.sqrt(periods) * excess.mean() / returns.std(ddof=1))


def sortino_ratio(returns: pd.Series, risk_free: float = 0.0,
                  periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free / periods
    downside = returns[returns < 0]
    dd = downside.std(ddof=1)
    if dd == 0 or np.isnan(dd):
        return 0.0
    return float(np.sqrt(periods) * excess.mean() / dd)


def max_drawdown(equity: pd.Series) -> float:
    """Return the maximum peak-to-trough drawdown as a negative fraction."""
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min())


def calmar_ratio(equity: pd.Series, periods: int = TRADING_DAYS) -> float:
    if len(equity) < 2:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0
    years = len(equity) / periods
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else 0.0
    mdd = abs(max_drawdown(equity))
    return float(cagr / mdd) if mdd > 0 else 0.0


def cagr(equity: pd.Series, periods: int = TRADING_DAYS) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    years = len(equity) / periods
    if years <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def volatility(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods))


def alpha_beta(returns: pd.Series, benchmark: pd.Series,
               periods: int = TRADING_DAYS) -> tuple[float, float]:
    """Annualised Jensen's alpha and beta from an OLS of returns on benchmark."""
    df = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    if len(df) < 2:
        return 0.0, 0.0
    y, x = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
    var = np.var(x, ddof=1)
    if var == 0:
        return 0.0, 0.0
    beta = float(np.cov(y, x, ddof=1)[0, 1] / var)
    alpha = float((y.mean() - beta * x.mean()) * periods)
    return alpha, beta


@dataclass
class TradeStats:
    num_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    payoff_ratio: float = 0.0


def trade_statistics(pnls: list[float]) -> TradeStats:
    if not pnls:
        return TradeStats()
    arr = np.asarray(pnls, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = len(wins) / len(arr)
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    payoff = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
    expectancy = float(arr.mean())
    return TradeStats(
        num_trades=len(arr),
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        expectancy=expectancy,
        payoff_ratio=payoff,
    )


@dataclass
class PerformanceReport:
    total_return: float = 0.0
    cagr: float = 0.0
    volatility: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    trades: TradeStats = None  # type: ignore[assignment]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def analyze(
    equity_curve: pd.Series,
    trade_pnls: list[float] | None = None,
    benchmark: pd.Series | None = None,
    risk_free: float = 0.0,
) -> PerformanceReport:
    """Produce a full :class:`PerformanceReport` from an equity curve."""
    equity_curve = equity_curve.dropna()
    if len(equity_curve) < 2:
        return PerformanceReport(trades=trade_statistics(trade_pnls or []))

    returns = _to_returns(equity_curve)
    report = PerformanceReport(
        total_return=float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0),
        cagr=cagr(equity_curve),
        volatility=volatility(returns),
        sharpe=sharpe_ratio(returns, risk_free),
        sortino=sortino_ratio(returns, risk_free),
        calmar=calmar_ratio(equity_curve),
        max_drawdown=max_drawdown(equity_curve),
        trades=trade_statistics(trade_pnls or []),
    )
    if benchmark is not None:
        report.alpha, report.beta = alpha_beta(returns, _to_returns(benchmark))
    return report
