# Setup Guide

## Prerequisites

- Python 3.10+
- (optional) Node 18+ for the dashboard
- (optional) Docker for the full stack

## 1. Install

```bash
git clone <repo-url> && cd quanttrade
python -m venv .venv && source .venv/bin/activate

# Core engine only:
pip install -e .

# Everything you'll typically want for development:
pip install -e ".[dev,web,data,security]"
```

## 2. Configure

```bash
cp .env.example .env
python -c "from quanttrade.core.security import generate_secret_key; print(generate_secret_key())"
# paste the result into QT_SECRET_KEY in .env
```

Edit `config/config.yaml` for non-secret settings (data provider, risk limits,
starting cash, …).

## 3. Smoke test

```bash
pytest                                  # run the test suite
python -m quanttrade.cli strategies     # list built-in strategies
python -m quanttrade.cli backtest --strategy ma_crossover --symbols AAPL,MSFT
python -m quanttrade.cli scan --symbols AAPL,MSFT,TSLA,NVDA,SPY
```

By default everything uses the built-in **synthetic** data provider, so it works
offline with zero external accounts.

## 4. Use real market data

```bash
pip install yfinance
export QT_DATA__PROVIDER=yfinance
python -m quanttrade.cli backtest --provider yfinance --strategy momentum --symbols AAPL
```

## 5. Run the API + dashboard

```bash
# Terminal 1 — backend
python -m quanttrade.cli serve          # http://localhost:8000  (/docs for OpenAPI)

# Terminal 2 — frontend
cd dashboard && npm install && npm run dev   # http://localhost:5173
```

## 6. Explore the examples

```bash
python examples/run_backtest.py
python examples/custom_strategy.py      # plug-in a new strategy
python examples/train_ml_model.py       # feature engineering + model selection
python examples/optimize_strategy.py    # grid / GA / walk-forward / Monte-Carlo
```

## Project layout

```
quanttrade/        core package (engine)
  core/            config, logging, events, security, enums, exceptions
  models/          domain dataclasses
  data/            market-data providers
  indicators/      technical-analysis engine
  strategies/      strategy framework + built-ins
  risk/            sizing + risk manager
  brokers/         broker interface + paper + live adapters
  portfolio/       tracking + analytics
  backtest/        engine + optimizers
  execution/       live/paper orchestration
  ml/              features, models, RL, sentiment, trainer
  scanner/         market scanner
  persistence/     SQLAlchemy ORM + repositories
  api/             FastAPI app + service layer
  cli.py           command-line interface
tests/             pytest suite
dashboard/         React + Vite + TS frontend
examples/          runnable example scripts
config/            config.yaml
docs/              documentation
```

## Disclaimer

This software is for **research and educational purposes**. No trading strategy
is guaranteed to be profitable; markets are unpredictable and live trading risks
real capital. Validate thoroughly in paper mode and trade at your own risk.
