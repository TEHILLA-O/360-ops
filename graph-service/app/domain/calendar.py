"""Northstar operating calendar. Holidays are explicit dates, not a guessed national feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


def uk_bank_holidays() -> frozenset[date]:
    return frozenset(
        {
            date(2026, 1, 1),
            date(2026, 4, 3),
            date(2026, 4, 6),
            date(2026, 5, 4),
            date(2026, 5, 25),
            date(2026, 8, 31),
            date(2026, 12, 25),
            date(2026, 12, 26),
            date(2027, 1, 1),
            date(2027, 3, 26),
            date(2027, 3, 29),
            date(2027, 5, 3),
            date(2027, 5, 31),
            date(2027, 8, 30),
            date(2027, 12, 27),
            date(2027, 12, 28),
        }
    )


@dataclass(frozen=True)
class BusinessCalendar:
    timezone: str = "Europe/London"
    start: time = time(8, 0)
    end: time = time(17, 30)
    holidays: frozenset[date] = uk_bank_holidays()

    @property
    def policy_version(self) -> str:
        return "2026.11.0"


DEFAULT_CALENDAR = BusinessCalendar()
