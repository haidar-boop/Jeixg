"""Repository layer.

Repositories translate between the framework-agnostic dataclasses in
:mod:`quanttrade.models` and the SQLAlchemy ORM rows in
:mod:`quanttrade.persistence.models`, keeping persistence concerns out of the
domain model and the trading engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..core.enums import (
    AssetClass,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
)
from ..models import Order, Trade
from .database import Database
from .models import (
    AuditLogORM,
    BarORM,
    EquityCurveORM,
    OrderORM,
    TradeORM,
)


class OrderRepository:
    """Persist and query orders."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, order: Order) -> None:
        with self.db.session() as s:
            row = s.get(OrderORM, order.id)
            if row is None:
                row = OrderORM(id=order.id)
                s.add(row)
            row.broker_order_id = order.broker_order_id
            row.symbol = order.symbol
            row.side = order.side.value
            row.order_type = order.order_type.value
            row.quantity = order.quantity
            row.limit_price = order.limit_price
            row.stop_price = order.stop_price
            row.status = order.status.value
            row.filled_quantity = order.filled_quantity
            row.avg_fill_price = order.avg_fill_price
            row.commission = order.commission
            row.strategy = order.strategy
            row.account_id = order.account_id or None
            row.created_at = order.created_at
            row.updated_at = order.updated_at

    def get(self, order_id: str) -> Order | None:
        with self.db.session() as s:
            row = s.get(OrderORM, order_id)
            return self._to_order(row) if row else None

    def list_open(self) -> list[Order]:
        active = {OrderStatus.PENDING.value, OrderStatus.SUBMITTED.value,
                  OrderStatus.PARTIALLY_FILLED.value}
        with self.db.session() as s:
            rows = s.query(OrderORM).filter(OrderORM.status.in_(active)).all()
            return [self._to_order(r) for r in rows]

    def update_status(self, order_id: str, status: OrderStatus) -> None:
        with self.db.session() as s:
            row = s.get(OrderORM, order_id)
            if row:
                row.status = status.value
                row.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _to_order(row: OrderORM) -> Order:
        return Order(
            id=row.id,
            broker_order_id=row.broker_order_id,
            symbol=row.symbol,
            side=OrderSide(row.side),
            quantity=row.quantity,
            order_type=OrderType(row.order_type),
            limit_price=row.limit_price,
            stop_price=row.stop_price,
            status=OrderStatus(row.status),
            filled_quantity=row.filled_quantity,
            avg_fill_price=row.avg_fill_price,
            commission=row.commission,
            strategy=row.strategy,
            account_id=row.account_id or "",
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class TradeRepository:
    """The trade journal."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, trade: Trade) -> None:
        with self.db.session() as s:
            if s.get(TradeORM, trade.id):
                return
            s.add(TradeORM(
                id=trade.id,
                symbol=trade.symbol,
                side=trade.side.value,
                quantity=trade.quantity,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                entry_time=trade.entry_time,
                exit_time=trade.exit_time,
                pnl=trade.pnl,
                commission=trade.commission,
                strategy=trade.strategy,
                return_pct=trade.return_pct,
                tags=list(trade.tags),
                notes=trade.notes,
            ))

    def list(self, symbol: str | None = None, strategy: str | None = None,
             limit: int = 100) -> list[Trade]:
        with self.db.session() as s:
            q = s.query(TradeORM)
            if symbol:
                q = q.filter(TradeORM.symbol == symbol)
            if strategy:
                q = q.filter(TradeORM.strategy == strategy)
            rows = q.order_by(TradeORM.exit_time.desc()).limit(limit).all()
            return [self._to_trade(r) for r in rows]

    def aggregate_pnl(self) -> float:
        with self.db.session() as s:
            from sqlalchemy import func
            total = s.query(func.coalesce(func.sum(TradeORM.pnl), 0.0)).scalar()
            return float(total or 0.0)

    @staticmethod
    def _to_trade(row: TradeORM) -> Trade:
        return Trade(
            id=row.id,
            symbol=row.symbol,
            side=PositionSide(row.side),
            quantity=row.quantity,
            entry_price=row.entry_price,
            exit_price=row.exit_price,
            entry_time=row.entry_time,
            exit_time=row.exit_time,
            pnl=row.pnl,
            commission=row.commission,
            strategy=row.strategy,
            tags=list(row.tags or []),
            notes=row.notes,
        )


class BarRepository:
    """Cache and retrieve historical OHLCV bars."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_bars(self, symbol: str, interval: str, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        count = 0
        with self.db.session() as s:
            existing = {
                ts for (ts,) in s.query(BarORM.timestamp)
                .filter(BarORM.symbol == symbol, BarORM.interval == interval).all()
            }
            for ts, bar in df.iterrows():
                pyts = pd.Timestamp(ts).to_pydatetime()
                if pyts in existing:
                    continue
                s.add(BarORM(
                    symbol=symbol, interval=interval, timestamp=pyts,
                    open=float(bar["open"]), high=float(bar["high"]),
                    low=float(bar["low"]), close=float(bar["close"]),
                    volume=float(bar["volume"]),
                ))
                count += 1
        return count

    def get_bars(self, symbol: str, interval: str,
                 start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
        with self.db.session() as s:
            q = s.query(BarORM).filter(BarORM.symbol == symbol, BarORM.interval == interval)
            if start:
                q = q.filter(BarORM.timestamp >= start)
            if end:
                q = q.filter(BarORM.timestamp <= end)
            rows = q.order_by(BarORM.timestamp.asc()).all()
            if not rows:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            df = pd.DataFrame(
                [{"timestamp": r.timestamp, "open": r.open, "high": r.high,
                  "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
            ).set_index("timestamp")
            return df


class AuditRepository:
    """Append-only security/activity audit log."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def log(self, actor: str, action: str, entity: str = "",
            entity_id: str | None = None, detail: dict | None = None,
            ip: str | None = None) -> None:
        with self.db.session() as s:
            s.add(AuditLogORM(actor=actor, action=action, entity=entity,
                              entity_id=entity_id, detail=detail or {}, ip=ip))

    def recent(self, limit: int = 100) -> list[dict]:
        with self.db.session() as s:
            rows = s.query(AuditLogORM).order_by(AuditLogORM.timestamp.desc()).limit(limit).all()
            return [{"timestamp": r.timestamp, "actor": r.actor, "action": r.action,
                     "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail}
                    for r in rows]


class EquityCurveRepository:
    """Time-series of account equity for the dashboard / analytics."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, equity: float, cash: float = 0.0, positions_value: float = 0.0,
               account_id: str = "default", when: datetime | None = None) -> None:
        with self.db.session() as s:
            s.add(EquityCurveORM(
                account_id=account_id, equity=equity, cash=cash,
                positions_value=positions_value,
                timestamp=when or datetime.now(timezone.utc),
            ))

    def history(self, account_id: str = "default") -> pd.Series:
        with self.db.session() as s:
            rows = (s.query(EquityCurveORM)
                    .filter(EquityCurveORM.account_id == account_id)
                    .order_by(EquityCurveORM.timestamp.asc()).all())
            if not rows:
                return pd.Series(dtype=float)
            return pd.Series([r.equity for r in rows],
                             index=pd.DatetimeIndex([r.timestamp for r in rows]),
                             name="equity")


__all__ = [
    "OrderRepository",
    "TradeRepository",
    "BarRepository",
    "AuditRepository",
    "EquityCurveRepository",
]
