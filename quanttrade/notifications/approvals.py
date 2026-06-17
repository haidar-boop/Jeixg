"""Trade-approval store + reply parsing for two-way SMS confirmation.

The bot (an always-on task) and the SMS webhook (the web app) are separate
processes, so they coordinate through a small JSON file guarded by a file lock.

Flow:
    1. Bot finds an opportunity -> ``create_request(symbol, ...)`` (status=pending)
       and texts the user "Found NVDA ... reply YES/NO".
    2. User replies -> the webhook calls ``record_decision(approved, symbol)``
       (status=approved/denied).
    3. Bot's next cycle -> ``pop_approved()`` executes the buy, then
       ``mark_executed(symbol)``; expired/denied requests enter a cooldown so the
       bot doesn't immediately re-ask.

Only **one** request is outstanding at a time, so a plain "YES"/"NO" reply is
unambiguous.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

try:  # POSIX file locking (PythonAnywhere / Linux); degrade gracefully elsewhere
    import fcntl

    _HAS_FCNTL = True
except Exception:  # pragma: no cover - non-POSIX
    _HAS_FCNTL = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE_PATH = PROJECT_ROOT / "approvals.json"

PENDING, APPROVED, DENIED, EXECUTED, EXPIRED = (
    "pending", "approved", "denied", "executed", "expired")

_YES = {"yes", "y", "buy", "ok", "okay", "yeah", "yep", "sure", "go"}
_NO = {"no", "n", "skip", "cancel", "stop", "nope"}


def parse_reply(body: str) -> tuple[bool | None, str | None]:
    """Parse an inbound SMS into ``(approved, symbol)``.

    ``approved`` is True/False, or None if the text isn't a yes/no. ``symbol`` is
    an explicit ticker if the user included one, else None (apply to the single
    outstanding request).
    """
    tokens = (body or "").strip().lower().split()
    if not tokens:
        return None, None
    decision: bool | None = None
    if tokens[0] in _YES:
        decision = True
    elif tokens[0] in _NO:
        decision = False
    else:
        return None, None  # not a yes/no -> ignore
    symbol = None
    for tok in tokens:
        t = tok.strip(".,!?").upper()
        if t.isalpha() and 1 <= len(t) <= 5 and t.lower() not in _YES | _NO:
            symbol = t
            break
    return decision, symbol


class ApprovalStore:
    """File-backed, lock-protected store of trade-approval requests."""

    def __init__(self, path: str | Path | None = None) -> None:
        import os
        self.path = Path(path or os.getenv("QT_APPROVALS_PATH") or DEFAULT_STORE_PATH)

    @contextmanager
    def _txn(self):
        self.path.touch(exist_ok=True)
        with open(self.path, "r+") as f:
            if _HAS_FCNTL:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                raw = f.read().strip()
                state = json.loads(raw) if raw else {"requests": {}}
                state.setdefault("requests", {})
                yield state, f
            finally:
                if _HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _commit(state: dict, f) -> None:
        f.seek(0)
        f.truncate()
        json.dump(state, f, indent=2)

    # --- bot side -------------------------------------------------------
    def has_outstanding(self) -> bool:
        with self._txn() as (state, _):
            return any(r["status"] == PENDING for r in state["requests"].values())

    def create_request(self, symbol: str, price: float, reason: str,
                       stop_loss: float | None = None, strength: float = 1.0) -> dict:
        with self._txn() as (state, f):
            req = {
                "symbol": symbol, "price": price, "reason": reason,
                "stop_loss": stop_loss, "strength": strength,
                "status": PENDING, "requested_at": time.time(), "decided_at": None,
            }
            state["requests"][symbol] = req
            self._commit(state, f)
            return dict(req)

    def pop_approved(self) -> list[dict]:
        with self._txn() as (state, _):
            return [dict(r) for r in state["requests"].values() if r["status"] == APPROVED]

    def mark_executed(self, symbol: str) -> None:
        with self._txn() as (state, f):
            if symbol in state["requests"]:
                state["requests"][symbol]["status"] = EXECUTED
                state["requests"][symbol]["decided_at"] = time.time()
                self._commit(state, f)

    def expire_old(self, ttl_seconds: float = 3600) -> int:
        with self._txn() as (state, f):
            now, n = time.time(), 0
            for r in state["requests"].values():
                if r["status"] == PENDING and now - r["requested_at"] > ttl_seconds:
                    r["status"] = EXPIRED
                    r["decided_at"] = now
                    n += 1
            if n:
                self._commit(state, f)
            return n

    def in_cooldown(self, symbol: str, cooldown_seconds: float = 3600) -> bool:
        """True if we recently asked/decided on this symbol (avoid spamming)."""
        with self._txn() as (state, _):
            r = state["requests"].get(symbol)
            if not r:
                return False
            if r["status"] == PENDING:
                return True
            if r["status"] in (DENIED, EXECUTED, EXPIRED) and r.get("decided_at"):
                return time.time() - r["decided_at"] < cooldown_seconds
            return False

    # --- webhook side ---------------------------------------------------
    def record_decision(self, approved: bool, symbol: str | None = None) -> dict | None:
        """Apply a yes/no to a specific symbol, or to the one pending request."""
        with self._txn() as (state, f):
            reqs = state["requests"]
            target = None
            if symbol and symbol in reqs and reqs[symbol]["status"] == PENDING:
                target = reqs[symbol]
            elif symbol is None:
                pending = [r for r in reqs.values() if r["status"] == PENDING]
                if len(pending) == 1:
                    target = pending[0]
                elif pending:
                    target = min(pending, key=lambda r: r["requested_at"])
            if target is None:
                return None
            target["status"] = APPROVED if approved else DENIED
            target["decided_at"] = time.time()
            self._commit(state, f)
            return dict(target)

    def list_requests(self) -> list[dict]:
        with self._txn() as (state, _):
            return [dict(r) for r in state["requests"].values()]
