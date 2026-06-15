# QuantTrade

A modular, production-grade **algorithmic trading platform** in Python — covering
backtesting, paper/forward testing, live execution, portfolio analytics, risk
management, machine learning, optimisation, a FastAPI service and a React
dashboard.

> **Disclaimer.** This is research/educational software. No strategy can
> reliably "do everything" or guarantee profits — markets are unpredictable and
> every strategy carries risk. Validate in paper mode; trade at your own risk.

---

## Why this exists

The goal is an *institutional-style* architecture — clean OOP, pluggable
components, risk-first execution, real analytics — where **the same strategy
code runs unchanged across backtest, paper and live**. The engine runs on a
minimal core (numpy / pandas / scikit-learn / SQLAlchemy); heavyweight or
account-bound integrations (FastAPI, yfinance, broker SDKs, TensorFlow) are
**optional and lazy-imported**, so `import quanttrade` always works.

## Quick start

```bash
pip install -e .                 # core engine (offline, synthetic data)
pytest                           # 60 tests
python -m quanttrade.cli backtest --strategy ma_crossover --symbols AAPL,MSFT
python examples/run_backtest.py
```

```python
from datetime import datetime
from quanttrade.data import create_data_provider
from quanttrade.strategies import MovingAverageCrossover
from quanttrade.backtest import BacktestEngine

data = {"AAPL": create_data_provider("synthetic").get_historical_bars(
    "AAPL", datetime(2019, 1, 1), datetime(2023, 1, 1))}
result = BacktestEngine(MovingAverageCrossover(fast=20, slow=50)).run(data)
print(result.summary())
```

## Feature matrix

| Area | What's implemented | Status |
|------|--------------------|--------|
| **Backtesting** | event-driven engine, no lookahead, commission + slippage | ✅ runnable |
| **Paper trading** | full simulated broker (market/limit/stop/stop-limit, long & short) | ✅ runnable |
| **Live trading** | broker-agnostic execution engine + adapters | ⚙️ needs broker creds |
| **Portfolio** | positions, equity curve, trade journal, multi-account model | ✅ runnable |
| **Risk** | daily-loss/drawdown halts, position/gross/sector caps, circuit breaker | ✅ runnable |
| **Position sizing** | fixed-fraction, fixed-risk, volatility-target, Kelly | ✅ runnable |
| **Analytics** | Sharpe, Sortino, Calmar, CAGR, max DD, alpha/beta, profit factor | ✅ runnable |
| **Indicators** | SMA/EMA/WMA, MACD, RSI, Stoch, ATR, Bollinger, Keltner, OBV, VWAP, MFI, Ichimoku, ADX, Supertrend, Fibonacci, S/R, trend & breakout | ✅ runnable |
| **Strategies** | trend-following, mean-reversion, momentum, breakout + plug-in registry | ✅ runnable |
| **ML / DL / RL** | feature pipeline, sklearn models, ensemble, auto-select, time-series CV; LSTM/MLP (TF, optional); Q-learning env + agent; sentiment | ✅ (DL optional) |
| **Optimisation** | grid search, genetic algorithm, walk-forward, Monte-Carlo | ✅ runnable |
| **Scanner** | universe ranking (momentum / RSI / volume / breakout) | ✅ runnable |
| **Brokers** | Paper ✅; Alpaca / IBKR / Tradier / TD-Schwab / Robinhood / Webull / generic REST | ⚙️ adapters (creds/SDK needed) |
| **Data** | synthetic (offline) ✅, yfinance ⚙️; provider ABC for more | ✅ / ⚙️ |
| **Persistence** | SQLAlchemy ORM + repositories (orders, trades, bars, audit, equity) | ✅ runnable |
| **API** | FastAPI REST + WebSocket, service layer | ⚙️ `pip install .[web]` |
| **Dashboard** | React + Vite + TS trading terminal | ⚙️ `npm install` |
| **Security** | env-based secrets, Fernet encryption, audit log | ✅ runnable |
| **Ops** | Docker + compose (Postgres/Redis), CLI, logging, config layering | ✅ |

✅ = works out of the box · ⚙️ = needs an optional dependency, SDK or credentials.

> **Scope note.** This is a substantial, coherent foundation rather than a
> finished hedge-fund stack. Live broker adapters implement the real API surface
> but require credentials/SDKs to exercise; deep-learning and transformer
> sentiment are scaffolded behind optional imports. The core
> data→signal→risk→execution→analytics loop is fully working and tested.

## Documentation

- [Setup guide](docs/setup_guide.md)
- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Database schema](docs/database_schema.md)
- [Deployment](docs/deployment.md)
- [Deploying on PythonAnywhere](docs/pythonanywhere.md)
- [Dashboard](dashboard/README.md)

## CLI

```bash
python -m quanttrade.cli strategies        # list strategies
python -m quanttrade.cli backtest  ...     # run a backtest
python -m quanttrade.cli optimize  ...     # grid-search params
python -m quanttrade.cli scan      ...     # market scanner
python -m quanttrade.cli init-db           # create DB tables
python -m quanttrade.cli serve             # run the API
```

## Running with Docker

```bash
cp .env.example .env
docker compose up --build      # API :8000, Postgres :5432, Redis :6379
```

## Testing

```bash
pytest                 # 60 tests across indicators, broker, risk, analytics,
                       # backtest, persistence, ML and strategies
```

## License

MIT.
