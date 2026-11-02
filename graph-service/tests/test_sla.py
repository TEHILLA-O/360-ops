from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.domain.calendar import BusinessCalendar
from app.domain.sla import (
    add_business_minutes,
    business_minutes_between,
    evaluate_sla,
    subtract_business_minutes,
)

LONDON = ZoneInfo("Europe/London")
CALENDAR = BusinessCalendar(
    holidays=frozenset({date(2026, 12, 25), date(2026, 12, 26), date(2026, 12, 28)}),
)


def at(year, month, day, hour, minute) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=LONDON)


def test_same_morning_is_not_a_raw_timestamp_subtraction():
    assert business_minutes_between(at(2026, 11, 2, 9, 0), at(2026, 11, 2, 12, 30), CALENDAR) == 210


def test_overnight_skips_closed_hours():
    # 17:00–17:30 Monday plus 08:00–09:00 Tuesday.
    assert business_minutes_between(at(2026, 11, 2, 17, 0), at(2026, 11, 3, 9, 0), CALENDAR) == 90


def test_weekend_contributes_nothing_until_monday():
    assert business_minutes_between(at(2026, 11, 7, 10, 0), at(2026, 11, 9, 9, 0), CALENDAR) == 60


def test_christmas_is_not_a_working_day():
    # Thu 24 Dec 17:00–17:30, then holidays and Sunday, then Mon 28 Dec is also listed as a holiday.
    # Next open morning is Tue 29 Dec 08:30.
    due = add_business_minutes(at(2026, 12, 24, 17, 0), 60, CALENDAR)
    assert due.astimezone(LONDON) == at(2026, 12, 29, 8, 30)


def test_pause_is_removed_from_elapsed_time():
    start = at(2026, 11, 2, 9, 0)
    end = at(2026, 11, 2, 12, 0)
    paused = business_minutes_between(start, end, CALENDAR, pauses=[(at(2026, 11, 2, 10, 0), at(2026, 11, 2, 11, 0))])
    assert paused == 120


def test_add_and_subtract_are_inverses_inside_business_hours():
    start = at(2026, 11, 2, 9, 15)
    assert subtract_business_minutes(add_business_minutes(start, 125, CALENDAR), 125, CALENDAR) == start.astimezone(timezone.utc)


def test_resolved_late_stays_breached_and_stops_the_clock():
    submitted = at(2026, 11, 2, 9, 0)
    completed = at(2026, 11, 2, 12, 0)
    result = evaluate_sla(
        status="resolved",
        submitted_at=submitted,
        now=at(2026, 11, 6, 9, 0),
        target_minutes=60,
        events=[],
        calendar=CALENDAR,
        completed_at=completed,
    )
    assert result["state"] == "breached"
    assert result["elapsed_business_minutes"] == 180
    assert result["met_resolution_target"] is False


def test_waiting_for_information_is_paused_before_the_deadline():
    result = evaluate_sla(
        status="awaiting_information",
        submitted_at=at(2026, 11, 2, 9, 0),
        now=at(2026, 11, 2, 10, 0),
        target_minutes=240,
        events=[],
        calendar=CALENDAR,
    )
    assert result["state"] == "paused"


def test_dst_summer_afternoon_still_uses_london_local_hours():
    # 15 July 2026 is BST (UTC+1). 16:00–17:30 local is 90 minutes, not a UTC mix-up.
    start = datetime(2026, 7, 15, 16, 0, tzinfo=LONDON)
    end = datetime(2026, 7, 15, 17, 30, tzinfo=LONDON)
    assert business_minutes_between(start, end, CALENDAR) == 90
    assert CALENDAR.start == time(8, 0)
