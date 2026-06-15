"""SQLAlchemy 2.0 ORM models for the QuantTrade persistence layer.

These ORM rows are the on-disk representation of the framework-agnostic
dataclasses defined in :mod:`quanttrade.models`. Conversion between the two is
the job of :mod:`quanttrade.persistence.repositories` -- the ORM layer stays
deliberately thin and stores enum *values* (plain strings) so the database is
readable without importing the application.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for every QuantTrade ORM model."""

    type_annotation_map = {
        dict[str, Any]: JSON,
        list[str]: JSON,
    }


class AccountORM(Base):
    """A brokerage / trading account."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    broker: Mapped[str] = mapped_column(String(64), default="")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OrderORM(Base):
    """Persisted order with its lifecycle state."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    broker_order_id: Mapped[str] = mapped_column(String(64), default="")
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_fill_price: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    strategy: Mapped[str] = mapped_column(String(64), default="")
    account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("accounts.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        Index("ix_orders_symbol_status", "symbol", "status"),
    )


class FillORM(Base):
    """An individual execution against an order."""

    __tablename__ = "fills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orders.id"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class PositionORM(Base):
    """A held position (open or historical)."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    last_price: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    asset_class: Mapped[str] = mapped_column(String(16), default="stock")
    account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("accounts.id"), nullable=True, index=True
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TradeORM(Base):
    """A completed round-trip trade -- the trade journal."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pnl: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    strategy: Mapped[str] = mapped_column(String(64), default="", index=True)
    return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class BarORM(Base):
    """A cached OHLCV bar for historical market data."""

    __tablename__ = "bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("symbol", "interval", "timestamp", name="uq_bar_sit"),
        Index("ix_bars_symbol_interval_ts", "symbol", "interval", "timestamp"),
    )


class SignalORM(Base):
    """A persisted strategy signal."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(16))
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy: Mapped[str] = mapped_column(String(64), default="", index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class AuditLogORM(Base):
    """Immutable security / activity audit log entry."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    actor: Mapped[str] = mapped_column(String(128), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EquityCurveORM(Base):
    """A point on an account's equity curve / portfolio history."""

    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    account_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("accounts.id"), nullable=True, index=True
    )
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    positions_value: Mapped[float] = mapped_column(Float, default=0.0)


__all__ = [
    "Base",
    "AccountORM",
    "OrderORM",
    "FillORM",
    "PositionORM",
    "TradeORM",
    "BarORM",
    "SignalORM",
    "AuditLogORM",
    "EquityCurveORM",
]
