# Architecture

QuantTrade is a modular, event-driven trading platform. The guiding principle is
that **the same strategy code runs unchanged across backtest, paper and live**,
differing only in the injected broker and data source.

## Layered design

```
                ┌─────────────────────────────────────────────┐
                │                  API / CLI                    │
                │   FastAPI + WebSocket  ·  python -m quanttrade │
                └───────────────┬───────────────────────────────┘
                                │
        ┌───────────────────────┼────────────────────────────────┐
        │                       │                                 │
┌───────▼────────┐   ┌──────────▼──────────┐         ┌────────────▼─────────┐
│   Backtest      │   │  Execution Engine    │         │   Optimization        │
│   Engine        │   │  (live / paper)      │         │  grid · GA · WFA · MC │
└───────┬────────┘   └──────────┬──────────┘         └───────────────────────┘
        │                       │
        │   ┌───────────────────┼───────────────────────────────┐
        │   │                   │                                │
┌───────▼───▼─┐   ┌─────────────▼────┐   ┌──────────┐   ┌────────▼────────┐
│  Strategy    │──▶│  Risk Manager     │──▶│  Broker  │──▶│   Portfolio      │
│  framework   │   │  sizing + limits  │   │  adapter │   │  + analytics     │
└──────┬───────┘   └──────────────────┘   └────┬─────┘   └────────┬─────────┘
       │                                        │                 │
┌──────▼───────┐   ┌──────────────┐   ┌─────────▼──────┐   ┌──────▼─────────┐
│  Indicators   │   │   ML / RL     │   │  Market Data   │   │  Persistence    │
│  (TA engine)  │   │  feature/model│   │  providers     │   │  (SQLAlchemy)   │
└───────────────┘   └──────────────┘   └────────────────┘   └─────────────────┘
                          shared:  core (config · logging · events · security · enums · models)
```

## Decision pipeline (identical in backtest and live)

```
market data ─▶ Strategy.generate_signals(window, context)
            ─▶ PositionSizer.size(...)              # how many shares
            ─▶ RiskManager.check_order(...)         # pre-trade gate
            ─▶ Broker.submit_order(...)             # paper / live execution
            ─▶ Portfolio.apply_fill(...)            # accounting + journal
            ─▶ RiskManager.update_equity(...)       # continuous monitor / halts
```

## Key modules

| Package | Responsibility |
|---------|----------------|
| `core` | config, logging, event bus, security/secrets, enums, exceptions |
| `models` | framework-agnostic dataclasses (Order, Fill, Position, Trade, Bar, …) |
| `data` | `MarketDataProvider` ABC + synthetic / yfinance providers + factory |
| `indicators` | from-scratch vectorised TA (RSI, MACD, ATR, Bollinger, Ichimoku, …) |
| `strategies` | `Strategy` ABC, plug-in registry, built-in strategies |
| `risk` | position sizers (fixed/risk/vol/Kelly) + layered risk manager |
| `brokers` | `Broker` ABC, paper engine, live adapters, factory |
| `portfolio` | position/equity tracking + performance analytics |
| `backtest` | event-driven engine + optimisers (grid/GA/WFA/Monte-Carlo) |
| `execution` | live/paper orchestration loop |
| `ml` | features, sklearn/DL models, ensembles, trainer, sentiment, RL |
| `scanner` | universe scanning / ranking |
| `persistence` | SQLAlchemy ORM + repositories |
| `api` | FastAPI REST + WebSocket; service layer |

## Design principles

- **No lookahead bias** — strategies only see data up to the current bar; ML
  labels are forward-looking while features are backward-only; time-series CV.
- **Single accounting authority** — `Portfolio.apply_fill` / `Position.apply_fill`
  own P&L math, shared by backtest, paper and live so results reconcile.
- **Dependency isolation** — the engine runs on numpy/pandas/sklearn/SQLAlchemy.
  FastAPI, yfinance, cryptography, broker SDKs and TensorFlow are *optional* and
  lazy-imported; a missing optional dep never breaks `import quanttrade`.
- **Extensibility** — providers, brokers, strategies, sizers and models are all
  pluggable behind ABCs + factories/registries.
- **Risk-first** — every order passes a risk gate; the portfolio is continuously
  monitored for daily-loss / drawdown breaches that halt trading.
