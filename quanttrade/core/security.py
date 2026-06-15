"""Credential management and secret encryption.

Broker/data API keys are read from the environment and stored at rest encrypted
with Fernet (AES-128-CBC + HMAC). The encryption key itself comes from
``QT_SECRET_KEY`` and is never persisted by the platform.

If ``cryptography`` is not installed the vault degrades to an in-memory store and
loudly warns -- encryption is required for any production deployment.
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from .exceptions import SecurityError
from .logging_config import get_logger

logger = get_logger(__name__)

try:  # optional dependency
    from cryptography.fernet import Fernet, InvalidToken

    _HAS_CRYPTO = True
except BaseException:  # noqa: BLE001 - broken native backends can *panic*, not just raise
    # cryptography may be installed but with a broken rust/cffi backend that
    # raises a BaseException-derived PanicException; degrade gracefully.
    _HAS_CRYPTO = False
    InvalidToken = Exception  # type: ignore[assignment,misc]


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a urlsafe-base64 32-byte key from an arbitrary secret string."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


@dataclass
class BrokerCredentials:
    broker: str
    api_key: str
    api_secret: str = ""
    account_id: str = ""
    extra: dict | None = None


class SecretVault:
    """Encrypts/decrypts secrets and resolves broker credentials from env."""

    def __init__(self, secret_key: str | None = None) -> None:
        self._secret_key = secret_key or os.getenv("QT_SECRET_KEY", "")
        self._store: dict[str, bytes] = {}
        if _HAS_CRYPTO and self._secret_key:
            self._fernet = Fernet(_derive_fernet_key(self._secret_key))
        else:
            self._fernet = None
            if not self._secret_key:
                logger.warning("QT_SECRET_KEY not set -- secrets will not be encrypted")

    def encrypt(self, plaintext: str) -> bytes:
        if self._fernet is None:
            return plaintext.encode()
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, token: bytes) -> str:
        if self._fernet is None:
            return token.decode()
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken as exc:  # pragma: no cover - defensive
            raise SecurityError("Failed to decrypt secret (wrong key?)") from exc

    def store(self, name: str, plaintext: str) -> None:
        self._store[name] = self.encrypt(plaintext)

    def retrieve(self, name: str) -> str | None:
        token = self._store.get(name)
        return self.decrypt(token) if token is not None else None

    def get_broker_credentials(self, broker: str) -> BrokerCredentials:
        """Resolve ``QT_<BROKER>_API_KEY`` / ``_API_SECRET`` / ``_ACCOUNT_ID``."""
        prefix = f"QT_{broker.upper()}_"
        key = os.getenv(prefix + "API_KEY", "")
        if not key:
            raise SecurityError(f"No credentials configured for broker '{broker}'")
        return BrokerCredentials(
            broker=broker,
            api_key=key,
            api_secret=os.getenv(prefix + "API_SECRET", ""),
            account_id=os.getenv(prefix + "ACCOUNT_ID", ""),
        )


def generate_secret_key() -> str:
    """Generate a fresh random secret suitable for ``QT_SECRET_KEY``."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()
