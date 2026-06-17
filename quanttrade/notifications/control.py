"""Runtime control flags shared between the SMS webhook and the bot.

Lets you text commands that the bot obeys on its next cycle:

    STOP / PAUSE      -> halt all new buying
    RESUME / START    -> resume trading
    SELL ALL / FLATTEN-> close every position and cancel open orders

Backed by a lock-protected JSON file (same approach as the approval store), so
the web app (which receives your texts) and the bot (a separate process) stay in
sync.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
    _HAS_FCNTL = True
except Exception:  # pragma: no cover - non-POSIX
    _HAS_FCNTL = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTROL_PATH = PROJECT_ROOT / "control.json"


class ControlStore:
    """Halt / resume / flatten flags persisted to disk."""

    def __init__(self, path: str | Path | None = None) -> None:
        import os
        self.path = Path(path or os.getenv("QT_CONTROL_PATH") or DEFAULT_CONTROL_PATH)

    @contextmanager
    def _txn(self):
        self.path.touch(exist_ok=True)
        with open(self.path, "r+") as f:
            if _HAS_FCNTL:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                raw = f.read().strip()
                state = json.loads(raw) if raw else {}
                state.setdefault("halted", False)
                state.setdefault("flatten", False)
                yield state, f
            finally:
                if _HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _commit(state, f):
        f.seek(0)
        f.truncate()
        json.dump(state, f, indent=2)

    def set_halt(self, halted: bool) -> None:
        with self._txn() as (state, f):
            state["halted"] = bool(halted)
            state["updated_at"] = time.time()
            self._commit(state, f)

    def is_halted(self) -> bool:
        with self._txn() as (state, _):
            return bool(state["halted"])

    def request_flatten(self) -> None:
        with self._txn() as (state, f):
            state["flatten"] = True
            state["updated_at"] = time.time()
            self._commit(state, f)

    def pop_flatten(self) -> bool:
        """Return whether a flatten was requested, clearing the flag."""
        with self._txn() as (state, f):
            requested = bool(state["flatten"])
            if requested:
                state["flatten"] = False
                self._commit(state, f)
            return requested

    def status(self) -> dict:
        with self._txn() as (state, _):
            return {"halted": bool(state["halted"]), "flatten": bool(state["flatten"])}
