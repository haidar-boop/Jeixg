# API Reference

The platform exposes a REST + WebSocket API via FastAPI
(`quanttrade/api/app.py`). Interactive OpenAPI docs are served at `/docs`
(Swagger UI) and `/redoc` once the server is running.

## Running

```bash
pip install -e ".[web]"
uvicorn quanttrade.api.app:app --reload   # http://localhost:8000
# or
python -m quanttrade.cli serve
```

On startup the service bootstraps a demo backtest so every endpoint returns
real data immediately.

## REST endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/api/health` | liveness + bootstrap status | `{status, bootstrapped, universe}` |
| GET | `/api/portfolio` | portfolio summary | `{equity, cash, positions_value, day_pnl, total_pnl}` |
| GET | `/api/positions` | open positions | `[{symbol, quantity, avg_price, last_price, unrealized_pnl, side}]` |
| GET | `/api/trades?limit=100` | trade journal | `[{symbol, side, quantity, entry_price, exit_price, pnl, return_pct, exit_time, strategy}]` |
| GET | `/api/equity_curve` | equity time-series | `[{timestamp, equity}]` |
| GET | `/api/strategies` | strategy performance | `[{name, status, pnl, sharpe, trades, win_rate}]` |
| GET | `/api/risk` | risk metrics | `{max_daily_loss_pct, current_drawdown, gross_exposure, var_95}` |
| GET | `/api/predictions` | AI predictions | `[{symbol, signal, probability, model}]` |
| GET | `/api/scanner?top_n=10` | scanner results | `[{symbol, score, reason, price, change_pct, metrics}]` |

## WebSocket

`GET /ws` — pushes a JSON snapshot every ~2s:

```json
{
  "type": "snapshot",
  "data": {
    "portfolio": { "equity": 114949.57, "...": "..." },
    "positions": [ { "symbol": "AAPL", "...": "..." } ]
  }
}
```

The dashboard's `useWebSocket` hook reconnects automatically with exponential
backoff.

## Example

```bash
curl http://localhost:8000/api/portfolio
curl "http://localhost:8000/api/scanner?top_n=5"
```

## Programmatic use (no HTTP server)

The service layer has no FastAPI dependency and can be used directly:

```python
from quanttrade.api import PlatformService

svc = PlatformService()
svc.bootstrap_demo()
print(svc.portfolio())
print(svc.scanner(top_n=5))
```
