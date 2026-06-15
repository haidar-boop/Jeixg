# Database Schema

QuantTrade persists state via SQLAlchemy 2.0 ORM models
(`quanttrade/persistence/models.py`). Enum values are stored as plain strings so
the database is readable without the application. The default engine is SQLite
(`sqlite:///quanttrade.db`); set `database.url` to a PostgreSQL DSN for
production (`postgresql+psycopg://user:pass@host:5432/quanttrade`).

Create all tables with:

```bash
python -m quanttrade.cli init-db
```

## Tables

### `accounts`
Trading accounts (supports multi-account / multi-broker).

| column | type | notes |
|--------|------|-------|
| id | str (PK) | account id |
| name | str | display name |
| broker | str | broker name |
| currency | str | base currency (default USD) |
| created_at | datetime | |

### `orders`
Order requests and their lifecycle.

| column | type | notes |
|--------|------|-------|
| id | str (PK) | platform order id |
| broker_order_id | str | id assigned by broker |
| symbol | str (idx) | |
| side | str | buy / sell |
| order_type | str | market / limit / stop / stop_limit / trailing_stop |
| quantity | float | |
| limit_price | float? | |
| stop_price | float? | |
| status | str (idx) | pending / submitted / filled / ... |
| filled_quantity | float | |
| avg_fill_price | float | |
| commission | float | |
| strategy | str | originating strategy |
| account_id | str (FK accounts.id) | |
| created_at / updated_at | datetime | |

### `fills`
Individual executions against an order.

| column | type | notes |
|--------|------|-------|
| id | str (PK) | |
| order_id | str (FK orders.id) | |
| symbol | str (idx) | |
| side | str | |
| quantity | float | |
| price | float | |
| commission | float | |
| timestamp | datetime | |

### `positions`
Open / historical positions with running P&L.

| column | type | notes |
|--------|------|-------|
| id | int (PK) | |
| symbol | str (idx) | |
| quantity | float | signed (negative = short) |
| avg_price | float | |
| last_price | float | |
| realized_pnl | float | |
| asset_class | str | |
| account_id | str (FK) | |
| opened_at | datetime | |
| closed_at | datetime? | null while open |

### `trades`
Completed round-trips — the **trade journal** powering analytics.

| column | type | notes |
|--------|------|-------|
| id | str (PK) | |
| symbol | str (idx) | |
| side | str | long / short |
| quantity | float | |
| entry_price / exit_price | float | |
| entry_time / exit_time | datetime (idx) | |
| pnl | float | net of commission |
| commission | float | |
| strategy | str (idx) | |
| return_pct | float | |
| tags | JSON | list of labels |
| notes | text | |

### `bars`
Historical OHLCV cache. Unique on `(symbol, interval, timestamp)`.

| column | type |
|--------|------|
| id | int (PK) |
| symbol | str (idx) |
| interval | str (idx) |
| timestamp | datetime (idx) |
| open/high/low/close | float |
| volume | float |

### `signals`
Persisted strategy signals (audit / research).

| column | type | notes |
|--------|------|-------|
| id | int (PK) | |
| symbol | str (idx) | |
| type | str | buy / sell / hold / close |
| strength | float | 0..1 conviction |
| price | float? | |
| strategy | str (idx) | |
| timestamp | datetime (idx) | |
| metadata | JSON | |

### `audit_log`
Append-only security / activity log.

| column | type | notes |
|--------|------|-------|
| id | int (PK) | |
| timestamp | datetime (idx) | |
| actor | str (idx) | who |
| action | str (idx) | what |
| entity / entity_id | str | target |
| detail | JSON | context |
| ip | str? | source ip |

### `equity_curve`
Time-series of account equity for the dashboard / analytics.

| column | type |
|--------|------|
| id | int (PK) |
| timestamp | datetime (idx) |
| account_id | str (FK) |
| equity | float |
| cash | float |
| positions_value | float |

## Relationships

```
accounts 1──* orders 1──* fills
accounts 1──* positions
accounts 1──* equity_curve
trades, bars, signals, audit_log are standalone (indexed for query speed)
```
