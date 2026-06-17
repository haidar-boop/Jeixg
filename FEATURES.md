# What QuantTrade Comes With

A complete feature inventory of the platform.

## Trading & execution
- **Live, paper, backtest, and forward-test** modes from the same strategy code
- **Built-in paper simulator** (no account needed) + **Alpaca** integration (paper & live)
- Additional broker adapters: Interactive Brokers, Tradier, TD/Schwab, Robinhood, Webull, and a generic REST template
- **24/7 automated bot** (runs as an always-on task)
- **Trusted core list** auto-trades; **everything else asks your permission**
- **Two-way SMS approval**: bot texts "I found NVDA… reply YES/NO", you reply to approve
- **SMS alerts on every trade** with profit/loss (via Twilio)
- Automatic exits (sell to lock profit / cut losses)
- Order types: market, limit, stop, stop-limit, trailing stop
- Fractional shares; long and short positions
- No duplicate orders (skips anything held or already pending)

## Risk management
- **Capital cap** — deploy at most $X regardless of account size
- Position sizing: fixed-fraction, fixed-risk (stop-based), volatility-target, Kelly criterion
- Max daily loss halt, max drawdown halt, intraday circuit breaker
- Per-position, gross-exposure, and sector exposure caps
- Stop-loss / take-profit support

## Strategies (and a plug-in framework for your own)
- Moving-average crossover, trend strength
- RSI mean-reversion (the active dip-buyer), Bollinger reversion
- Momentum, Donchian breakout

## Technical indicators (30+)
- Moving averages: SMA, EMA, WMA, VWAP
- Momentum: RSI, Stochastic, ROC, Williams %R, CCI, MACD
- Volatility: ATR, Bollinger Bands, Keltner Channels, historical volatility
- Volume: OBV, MFI, Accumulation/Distribution, Volume Profile
- Trend/structure: ADX, Supertrend, Ichimoku Cloud, Fibonacci levels,
  support/resistance, trend detection, breakout detection

## Market scanning
- Scans a universe (~40 liquid stocks/ETFs) ranking momentum, RSI extremes,
  volume spikes and breakouts
- Watchlist showing the bot's current signal + RSI + trend per stock

## AI / machine learning
- Feature-engineering pipeline (returns, volatility, indicator features)
- Models: Random Forest, Gradient Boosting, Logistic/Linear/Ridge regression
- Ensemble models + automatic best-model selection
- Time-series cross-validation (no lookahead)
- News/social **sentiment analysis**
- **Reinforcement-learning** trading environment + Q-learning agent
- Optional deep learning (LSTM / MLP) when TensorFlow is installed

## Backtesting & research
- Event-driven backtest engine (commission + slippage, no lookahead)
- **Grid search** and **genetic-algorithm** parameter optimization
- **Walk-forward analysis** (out-of-sample robustness)
- **Monte-Carlo simulation** (outcome distribution / risk of loss)
- Performance analytics: Sharpe, Sortino, Calmar, CAGR, max drawdown,
  alpha/beta, profit factor, win rate, expectancy

## Web dashboard (live)
- Account summary: equity, cash, buying power, day P&L, unrealized P&L
- Real equity-curve chart
- Live positions with unrealized P&L
- Watchlist of the bot's live signals
- Orders (mirrors Alpaca — cancelled orders drop off)
- Market scanner, AI predictions, risk controls
- Market open/closed indicator, connection status, auto-refresh

## Notifications
- Twilio SMS (trade alerts + approval), with an always-on log fallback

## Platform & infrastructure
- Layered configuration (file + environment overrides)
- Structured logging
- Encrypted secret/credential vault
- Database (SQLAlchemy): orders, trades, bars cache, audit log, equity history
- Command-line interface (`backtest`, `scan`, `optimize`, `serve`, …)
- FastAPI REST + WebSocket API; Flask WSGI app for PythonAnywhere
- Docker + docker-compose (Postgres/Redis)
- 80+ automated tests
- Full documentation (setup, architecture, API, database, deployment,
  PythonAnywhere, this feature list)

## One-command helpers
- `setup.sh` — install everything
- `start_bot.sh` — run the bot (your settings at the top)
- `update.sh` — pull the latest code
