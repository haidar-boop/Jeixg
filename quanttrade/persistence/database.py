"""Engine / session management for the persistence layer.

Wraps a SQLAlchemy engine and sessionmaker behind a small :class:`Database`
facade so the rest of the codebase never touches engine internals. A process
wide singleton is provided via :func:`get_database`, but an explicit ``url`` can
always be passed (e.g. ``sqlite:///:memory:`` for tests).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_config
from ..core.logging_config import get_logger
from .models import Base

logger = get_logger(__name__)


class Database:
    """Thin facade over a SQLAlchemy engine + session factory."""

    def __init__(self, url: str | None = None, echo: bool | None = None) -> None:
        cfg = get_config()
        self.url = url or cfg.get("database.url", "sqlite:///quanttrade.db")
        self.echo = cfg.get("database.echo", False) if echo is None else echo

        connect_args: dict = {}
        engine_kwargs: dict = {}
        if self.url.startswith("sqlite"):
            # Allow cross-thread use (FastAPI / background workers) and keep an
            # in-memory database alive for the life of the engine.
            connect_args["check_same_thread"] = False
            if ":memory:" in self.url or self.url == "sqlite://":
                from sqlalchemy.pool import StaticPool

                engine_kwargs["poolclass"] = StaticPool

        self._engine: Engine = create_engine(
            self.url, echo=self.echo, future=True,
            connect_args=connect_args, **engine_kwargs,
        )
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, future=True,
        )
        logger.debug("Database initialised url=%s echo=%s", self.url, self.echo)

    def get_engine(self) -> Engine:
        return self._engine

    def create_all(self) -> None:
        """Create every table defined on :class:`Base`."""
        Base.metadata.create_all(self._engine)
        logger.info("Created all tables on %s", self.url)

    def drop_all(self) -> None:
        """Drop every table defined on :class:`Base`."""
        Base.metadata.drop_all(self._engine)
        logger.info("Dropped all tables on %s", self.url)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Context manager yielding a session, committing on success."""
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()


_database: Database | None = None


def get_database(url: str | None = None) -> Database:
    """Return the process-wide :class:`Database` singleton."""
    global _database
    if _database is None:
        _database = Database(url)
    return _database
