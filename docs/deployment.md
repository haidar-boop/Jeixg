# Deployment Guide

## 1. Docker Compose (recommended for a full local stack)

Brings up the API engine, PostgreSQL, Redis and (optionally) the dashboard.

```bash
cp .env.example .env          # fill in secrets / broker keys
docker compose up --build     # API on :8000, Postgres on :5432
docker compose --profile frontend up --build   # also build the dashboard
```

The `api` service waits for Postgres to be healthy, then serves
`uvicorn quanttrade.api.app:app` on port 8000 with a `/api/health` healthcheck.

## 2. Standalone container

```bash
docker build -t quanttrade .
docker run --env-file .env -p 8000:8000 quanttrade
```

## 3. Bare-metal / VM

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[web,data,security]"
python -m quanttrade.cli init-db
uvicorn quanttrade.api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

Run behind nginx/Caddy as a reverse proxy terminating TLS and forwarding `/api`
and `/ws` to the app. Use a process manager (systemd / supervisor) for restarts.

## Configuration & secrets

- Non-secret config lives in `config/config.yaml`.
- Override anything with `QT_`-prefixed env vars (`__` denotes nesting), e.g.
  `QT_RISK__MAX_DAILY_LOSS_PCT=0.02`.
- **Secrets** (broker API keys, DB passwords, `QT_SECRET_KEY`) come from the
  environment / `.env` only — never commit them. `QT_SECRET_KEY` encrypts stored
  credentials at rest (Fernet). Generate one:
  ```bash
  python -c "from quanttrade.core.security import generate_secret_key; print(generate_secret_key())"
  ```

## Production database

Set a PostgreSQL DSN:

```bash
export QT_DATABASE__URL="postgresql+psycopg://quant:secret@db:5432/quanttrade"
python -m quanttrade.cli init-db
```

## Scaling notes

- The API is stateless behind the database — run multiple `uvicorn` workers /
  replicas behind a load balancer.
- Keep the live `TradingEngine` as a single owner per account to avoid duplicate
  orders; scale horizontally by sharding accounts/strategies across workers.
- Redis (included in compose) is the recommended broker/cache for distributing
  market-data fan-out and rate-limiting in a multi-process deployment.

## Going live — checklist

1. Start in `paper` mode and validate fills/accounting against the broker.
2. Configure conservative `risk.*` limits; verify the daily-loss / drawdown
   halts trip as expected.
3. Set real broker credentials via env vars; confirm `connect()` succeeds.
4. Enable the audit log and monitor `logs/quanttrade.log` (or JSON logs).
5. Only then flip `trading.mode: live`. **Trade at your own risk.**
