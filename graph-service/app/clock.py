"""Time source. Tests and the seeder can pass explicit event times."""

from __future__ import annotations

from datetime import datetime, timezone


class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
