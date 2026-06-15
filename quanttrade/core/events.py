"""Lightweight in-process event bus.

The platform is event-driven: data providers publish ``MARKET_DATA`` events,
strategies publish ``SIGNAL`` events, the execution engine publishes ``ORDER`` /
``FILL`` events, and risk publishes ``RISK_BREACH`` events. Components subscribe
to the event types they care about, which keeps them decoupled and testable.

Both synchronous and asyncio-based dispatch are supported.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .enums import EventType
from .logging_config import get_logger

logger = get_logger(__name__)

Handler = Callable[["Event"], Any]
AsyncHandler = Callable[["Event"], Awaitable[Any]]


@dataclass
class Event:
    type: EventType
    payload: Any = None
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Synchronous pub/sub bus. Handler exceptions are isolated and logged."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        for handler in list(self._subscribers.get(event.type, [])):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - isolate misbehaving subscribers
                logger.exception("Event handler failed for %s", event.type)

    def emit(self, event_type: EventType, payload: Any = None, source: str = "") -> None:
        self.publish(Event(event_type, payload, source))


class AsyncEventBus:
    """Asyncio variant for the live/streaming path."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[AsyncHandler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: AsyncHandler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._subscribers.get(event.type, [])
        if not handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in handlers), return_exceptions=True
        )
        for res in results:
            if isinstance(res, Exception):
                logger.error("Async handler failed for %s: %r", event.type, res)
