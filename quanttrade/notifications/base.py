"""Notification framework.

Lets the bot push alerts (e.g. "BOT made a trade") to external channels. A
:class:`Notifier` has one job: ``send(subject, message)``. Concrete channels:

* :class:`LogNotifier`    -- always available; writes to the log (default).
* :class:`TwilioSMSNotifier` -- real text messages via Twilio.
* :class:`CompositeNotifier` -- fan-out to several channels at once.

Channels never raise into the trading loop -- a failed notification is logged
and swallowed so a texting outage can't take the bot down.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.logging_config import get_logger

logger = get_logger(__name__)


class Notifier(ABC):
    """Abstract notification channel."""

    name: str = "base"

    @abstractmethod
    def _send(self, subject: str, message: str) -> None: ...

    def send(self, subject: str, message: str) -> bool:
        """Send a notification; never raises. Returns True on success."""
        try:
            self._send(subject, message)
            return True
        except Exception:  # noqa: BLE001 - notifications must not break trading
            logger.exception("Notification via %s failed", self.name)
            return False


class LogNotifier(Notifier):
    """Fallback channel that just logs -- works with zero configuration."""

    name = "log"

    def _send(self, subject: str, message: str) -> None:
        logger.info("NOTIFY [%s] %s", subject, message)


class CompositeNotifier(Notifier):
    """Sends through every configured channel."""

    name = "composite"

    def __init__(self, channels: list[Notifier]) -> None:
        self.channels = channels

    def _send(self, subject: str, message: str) -> None:
        for ch in self.channels:
            ch.send(subject, message)
