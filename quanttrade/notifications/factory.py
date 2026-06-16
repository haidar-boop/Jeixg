"""Build the right notifier from the environment / config.

If Twilio credentials are present, you get SMS (plus a log copy). Otherwise you
get the log-only notifier, so the bot always has a working notifier and never
fails just because texting isn't set up.
"""
from __future__ import annotations

from ..core.logging_config import get_logger
from .base import CompositeNotifier, LogNotifier, Notifier
from .sms import TwilioSMSNotifier

logger = get_logger(__name__)


def create_notifier() -> Notifier:
    """Return an SMS+log notifier if Twilio is configured, else log-only."""
    channels: list[Notifier] = [LogNotifier()]
    if TwilioSMSNotifier.is_configured():
        try:
            channels.append(TwilioSMSNotifier())
            logger.info("SMS notifications enabled (Twilio)")
        except Exception:  # noqa: BLE001
            logger.exception("Twilio configured but failed to initialise; SMS disabled")
    else:
        logger.info("SMS not configured -- trade alerts will only appear in the log")
    return channels[0] if len(channels) == 1 else CompositeNotifier(channels)
