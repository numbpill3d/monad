# SPDX-License-Identifier: GPL-3.0-or-later
"""Developer-fee scheduler.

Monad mines to the developer for FEE_RATE (2%) of *hashing time*.  Time is
only counted while the miner is actually connected and producing hashes, so
RandomX initialisation and reconnects are never billed.

The ledger keeps lifetime totals (persisted to disk), so short sessions add
up correctly and stopping in the middle of a developer slice only counts the
part that was actually mined.  Fee slices are batched: the miner switches to
the developer pool once the owed time reaches SLICE_SECONDS and switches
back as soon as the debt is paid (roughly 1 minute every 49 minutes).
"""
import json
import os
from dataclasses import dataclass, asdict

FEE_RATE = 0.02
SLICE_SECONDS = 60.0
# If the developer pool can't be reached, give up after this long, go back
# to the user's pool (the debt is kept, nothing is billed) and retry later.
DEV_CONNECT_TIMEOUT = 90.0
DEV_RETRY_BACKOFF = 600.0

USER = "user"
DEV = "dev"


@dataclass
class Ledger:
    user_seconds: float = 0.0
    dev_seconds: float = 0.0

    @property
    def debt(self) -> float:
        """Seconds still owed to the developer (negative = credit)."""
        total = self.user_seconds + self.dev_seconds
        return FEE_RATE * total - self.dev_seconds

    @property
    def ratio(self) -> float:
        total = self.user_seconds + self.dev_seconds
        return self.dev_seconds / total if total else 0.0


class FeeScheduler:
    def __init__(self, ledger: Ledger | None = None):
        self.ledger = ledger or Ledger()
        self.mode = USER
        self._dev_waiting = 0.0
        self._backoff = 0.0

    def tick(self, dt: float, hashing: bool) -> str:
        """Account dt seconds in the current mode; return the mode to use next."""
        if hashing and dt > 0:
            if self.mode == DEV:
                self.ledger.dev_seconds += dt
                self._dev_waiting = 0.0
            else:
                self.ledger.user_seconds += dt
        elif self.mode == DEV:
            self._dev_waiting += max(dt, 0.0)
        if self.mode == USER and self._backoff > 0:
            self._backoff = max(0.0, self._backoff - max(dt, 0.0))
        debt = self.ledger.debt
        if self.mode == USER and debt >= SLICE_SECONDS and self._backoff <= 0:
            self.mode = DEV
            self._dev_waiting = 0.0
        elif self.mode == DEV and debt <= 0:
            self.mode = USER
        elif self.mode == DEV and self._dev_waiting >= DEV_CONNECT_TIMEOUT:
            # developer pool unreachable: never hold the user's miner hostage
            self.mode = USER
            self._dev_waiting = 0.0
            self._backoff = DEV_RETRY_BACKOFF
        return self.mode

    def reset_session(self):
        """Called when mining stops: the next session starts on the user's pool;
        any remaining debt is carried over and paid later."""
        self.mode = USER
        self._dev_waiting = 0.0
        self._backoff = 0.0

    @property
    def dev_seconds_left(self) -> float:
        return max(0.0, self.ledger.debt) if self.mode == DEV else 0.0


def load_ledger(path: str) -> Ledger:
    try:
        with open(path) as f:
            d = json.load(f)
        return Ledger(float(d.get("user_seconds", 0)), float(d.get("dev_seconds", 0)))
    except (OSError, ValueError, TypeError):
        return Ledger()


def save_ledger(path: str, ledger: Ledger):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(asdict(ledger), f)
    os.replace(tmp, path)
