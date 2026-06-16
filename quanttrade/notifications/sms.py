"""Text-message (SMS) notifications via Twilio.

Uses Twilio's REST API directly over HTTPS (``requests``) so there's no hard
dependency on the ``twilio`` SDK. Credentials come from the environment / ``.env``:

    QT_TWILIO_ACCOUNT_SID   your Twilio Account SID  (starts with "AC...")
    QT_TWILIO_AUTH_TOKEN    your Twilio Auth Token
    QT_TWILIO_FROM          the Twilio phone number to send FROM (e.g. +15551234567)
    QT_TWILIO_TO            your cell number to send TO          (e.g. +15559876543)

Get these free at https://www.twilio.com/try-twilio
"""
from __future__ import annotations

import os

from ..core.exceptions import QuantTradeError
from ..core.logging_config import get_logger
from .base import Notifier

logger = get_logger(__name__)

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class TwilioSMSNotifier(Notifier):
    """Send SMS text messages through Twilio."""

    name = "twilio_sms"

    def __init__(self, account_sid: str | None = None, auth_token: str | None = None,
                 from_number: str | None = None, to_number: str | None = None) -> None:
        self.account_sid = account_sid or os.getenv("QT_TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("QT_TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.getenv("QT_TWILIO_FROM", "")
        self.to_number = to_number or os.getenv("QT_TWILIO_TO", "")
        if not all([self.account_sid, self.auth_token, self.from_number, self.to_number]):
            raise QuantTradeError(
                "Twilio SMS not configured. Set QT_TWILIO_ACCOUNT_SID, "
                "QT_TWILIO_AUTH_TOKEN, QT_TWILIO_FROM and QT_TWILIO_TO."
            )

    @classmethod
    def is_configured(cls) -> bool:
        return all(os.getenv(k) for k in (
            "QT_TWILIO_ACCOUNT_SID", "QT_TWILIO_AUTH_TOKEN",
            "QT_TWILIO_FROM", "QT_TWILIO_TO",
        ))

    def _send(self, subject: str, message: str) -> None:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - optional
            raise QuantTradeError("Texting needs `requests` (pip install requests)") from exc

        body = f"{subject}\n{message}" if subject else message
        resp = requests.post(
            TWILIO_API.format(sid=self.account_sid),
            data={"From": self.from_number, "To": self.to_number, "Body": body[:1500]},
            auth=(self.account_sid, self.auth_token),
            timeout=15,
        )
        if resp.status_code >= 400:
            raise QuantTradeError(f"Twilio error {resp.status_code}: {resp.text}")
        logger.debug("SMS sent to %s", self.to_number)
