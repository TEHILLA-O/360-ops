"""Business-hour SLA arithmetic.

Elapsed time is the overlap of the interval with open weekdays, minus paused
intervals. It is not the raw difference of two timestamps.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.calendar import BusinessCalendar

TERMINAL_COMPLETED = {"resolved", "closed"}
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}


def higher_priority(left: str, right: str) -> str:
    return left if PRIORITY_RANK.get(left, 1) >= PRIORITY_RANK.get(right, 1) else right


def business_intervals(
    start: datetime,
    end: datetime,
    calendar: BusinessCalendar,
) -> list[tuple[datetime, datetime]]:
    tz = ZoneInfo(calendar.timezone)
    start_local = start.astimezone(tz)
    end_local = end.astimezone(tz)
    if end_local <= start_local:
        return []
    intervals: list[tuple[datetime, datetime]] = []
    day = start_local.date()
    last = end_local.date()
    while day <= last:
        if day.weekday() < 5 and day not in calendar.holidays:
            opened = datetime.combine(day, calendar.start, tz)
            closed = datetime.combine(day, calendar.end, tz)
            segment_start = max(start_local, opened)
            segment_end = min(end_local, closed)
            if segment_end > segment_start:
                intervals.append((segment_start, segment_end))
        day += timedelta(days=1)
    return intervals


def _subtract(
    base: list[tuple[datetime, datetime]],
    cuts: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    segments = list(base)
    for cut_start, cut_end in cuts:
        nxt: list[tuple[datetime, datetime]] = []
        for seg_start, seg_end in segments:
            if cut_end <= seg_start or cut_start >= seg_end:
                nxt.append((seg_start, seg_end))
                continue
            if cut_start > seg_start:
                nxt.append((seg_start, cut_start))
            if cut_end < seg_end:
                nxt.append((cut_end, seg_end))
        segments = nxt
    return segments


def _minutes(intervals: list[tuple[datetime, datetime]]) -> int:
    return sum(int((end - start).total_seconds() // 60) for start, end in intervals)


def business_minutes_between(
    start: datetime,
    end: datetime,
    calendar: BusinessCalendar,
    pauses: list[tuple[datetime, datetime]] | None = None,
) -> int:
    base = business_intervals(start, end, calendar)
    cuts: list[tuple[datetime, datetime]] = []
    for pause_start, pause_end in pauses or []:
        cuts.extend(business_intervals(pause_start, pause_end, calendar))
    return _minutes(_subtract(base, cuts))


def subtract_business_minutes(end: datetime, minutes: int, calendar: BusinessCalendar) -> datetime:
    if minutes < 0:
        raise ValueError("minutes must be >= 0")
    tz = ZoneInfo(calendar.timezone)
    cursor = end.astimezone(tz)
    remaining = minutes
    for _ in range(400):
        if remaining == 0:
            return cursor.astimezone(timezone.utc)
        day = cursor.date()
        if day.weekday() < 5 and day not in calendar.holidays:
            opened = datetime.combine(day, calendar.start, tz)
            closed = datetime.combine(day, calendar.end, tz)
            if cursor > closed:
                cursor = closed
            if cursor > opened:
                available = int((cursor - opened).total_seconds() // 60)
                if remaining <= available:
                    return (cursor - timedelta(minutes=remaining)).astimezone(timezone.utc)
                remaining -= available
        cursor = datetime.combine(day - timedelta(days=1), calendar.end, tz)
    raise ValueError("Could not walk back the requested business minutes")


def add_business_minutes(start: datetime, minutes: int, calendar: BusinessCalendar) -> datetime:
    if minutes < 0:
        raise ValueError("minutes must be >= 0")
    tz = ZoneInfo(calendar.timezone)
    cursor = start.astimezone(tz)
    remaining = minutes
    for _ in range(400):
        if remaining == 0:
            return cursor.astimezone(timezone.utc)
        day = cursor.date()
        if day.weekday() < 5 and day not in calendar.holidays:
            opened = datetime.combine(day, calendar.start, tz)
            closed = datetime.combine(day, calendar.end, tz)
            if cursor < opened:
                cursor = opened
            if cursor < closed:
                available = int((closed - cursor).total_seconds() // 60)
                if remaining <= available:
                    return (cursor + timedelta(minutes=remaining)).astimezone(timezone.utc)
                remaining -= available
        cursor = datetime.combine(day + timedelta(days=1), calendar.start, tz)
    raise ValueError("SLA deadline did not fall within 400 calendar days")


def pause_intervals(
    events: list[dict],
    now: datetime,
) -> list[tuple[datetime, datetime]]:
    """Rebuild customer-wait pauses from status transitions. Events are not edited."""
    ordered = sorted(events, key=lambda item: item["occurred_at"])
    intervals: list[tuple[datetime, datetime]] = []
    pause_started: datetime | None = None
    for event in ordered:
        new_state = event.get("new_state")
        moment = datetime.fromisoformat(event["occurred_at"])
        if new_state == "awaiting_information" and pause_started is None:
            pause_started = moment
        elif new_state and new_state != "awaiting_information" and pause_started is not None:
            if moment > pause_started:
                intervals.append((pause_started, moment))
            pause_started = None
    if pause_started is not None and now > pause_started:
        intervals.append((pause_started, now))
    return intervals


def evaluate_sla(
    *,
    status: str,
    submitted_at: datetime,
    now: datetime,
    target_minutes: int | None,
    events: list[dict],
    calendar: BusinessCalendar,
    completed_at: datetime | None = None,
) -> dict:
    """Clock stops at completion so a resolved case does not keep ageing."""
    clock_end = now
    if status in TERMINAL_COMPLETED | {"cancelled"} and completed_at is not None:
        clock_end = completed_at
    pauses = pause_intervals(events, clock_end)
    elapsed = business_minutes_between(submitted_at, clock_end, calendar, pauses)
    currently_paused = status == "awaiting_information"
    met: bool | None
    if target_minutes is None:
        met = None
    else:
        met = elapsed < target_minutes
    if status == "cancelled":
        state = "not_applicable"
    elif target_minutes is not None and elapsed >= target_minutes:
        state = "breached"
    elif status in TERMINAL_COMPLETED:
        state = "completed"
    elif currently_paused:
        state = "paused"
    elif target_minutes is None:
        state = "not_applicable"
    else:
        remaining = (target_minutes or 0) - elapsed
        warn = max(60, math.ceil((target_minutes or 0) * 0.2))
        state = "approaching" if remaining <= warn else "healthy"
    due_at = (
        add_business_minutes(submitted_at, target_minutes, calendar).isoformat()
        if target_minutes is not None
        else None
    )
    return {
        "state": state,
        "elapsed_business_minutes": elapsed,
        "target_business_minutes": target_minutes,
        "due_at": due_at,
        "paused": currently_paused,
        "met_resolution_target": met,
    }
