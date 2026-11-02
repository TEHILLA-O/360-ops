"""Operational measures computed from stored cases. Rates are null when the denominator is zero."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.calendar import BusinessCalendar
from app.domain.sla import business_minutes_between, pause_intervals

OPEN_STATUSES = {
    "new",
    "awaiting_information",
    "classified",
    "assigned",
    "awaiting_approval",
    "approved",
    "in_progress",
    "awaiting_fulfilment",
}

DEFINITIONS = {
    "received": "Cases whose submission timestamp falls inside the window.",
    "completed": "Cases whose completion timestamp falls inside the window and whose status is resolved or closed.",
    "avg_first_response_business_minutes": "Mean business minutes from submission to the first classification, routing, clarification, or acceptance event. Null when none exist.",
    "avg_resolution_business_minutes": "Mean business minutes from submission to completion for cases completed in the window. Pauses while awaiting information are excluded.",
    "sla_compliance_rate": "Completed cases in the window that met the resolution target, divided by completed cases in the window.",
    "avg_approval_turnaround_business_minutes": "Mean business minutes from approval request to recorded decision, for decisions inside the window.",
    "recorded_integration_success_rate": "Succeeded integration runs divided by succeeded plus failed runs in the window. Duplicate suppressions are excluded. This is not a Power Automate service metric.",
    "escalation_rate": "Cases submitted in the window that have at least one escalation, divided by cases submitted in the window.",
    "reopened": "Count of case_reopened audit events inside the window.",
    "recorded_integration_failure_rate": "Failed integration runs divided by succeeded plus failed runs in the window.",
    "approval_wait_share": "Business minutes spent in awaiting approval, grouped by the owning department, divided by all such waiting minutes in the window.",
}


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _in_window(moment: datetime | None, start: datetime, end: datetime) -> bool:
    return moment is not None and start <= moment <= end


def _mean(values: list[int]) -> int | None:
    if not values:
        return None
    return round(sum(values) / len(values))


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _approval_intervals(events: list[dict]) -> list[tuple[datetime, datetime, str | None]]:
    ordered = sorted(events, key=lambda item: item["occurred_at"])
    intervals = []
    started: datetime | None = None
    for event in ordered:
        moment = datetime.fromisoformat(event["occurred_at"])
        if event.get("new_state") == "awaiting_approval" and started is None:
            started = moment
        elif started is not None and event.get("new_state") and event.get("new_state") != "awaiting_approval":
            if moment > started:
                intervals.append((started, moment))
            started = None
    return intervals


def build_analytics(
    *,
    cases: list[dict],
    events_by_case: dict[str, list[dict]],
    approvals: list[dict],
    integrations: list[dict],
    escalations: list[dict],
    start: datetime,
    end: datetime,
    calendar: BusinessCalendar,
) -> dict:
    received = [case for case in cases if _in_window(_parse(case["submitted_at"]), start, end)]
    completed = [
        case
        for case in cases
        if case["status"] in {"resolved", "closed"} and _in_window(_parse(case.get("completed_at")), start, end)
    ]
    first_response_samples: list[int] = []
    resolution_samples: list[int] = []
    response_actions = {"request_classified", "clarification_requested", "case_routed", "work_accepted"}
    for case in received:
        events = events_by_case.get(case["id"], [])
        submitted = datetime.fromisoformat(case["submitted_at"])
        responses = [
            datetime.fromisoformat(event["occurred_at"])
            for event in events
            if event["action"] in response_actions
        ]
        if responses:
            first_response_samples.append(
                business_minutes_between(submitted, min(responses), calendar)
            )
    for case in completed:
        events = events_by_case.get(case["id"], [])
        submitted = datetime.fromisoformat(case["submitted_at"])
        finished = datetime.fromisoformat(case["completed_at"])
        resolution_samples.append(
            business_minutes_between(submitted, finished, calendar, pause_intervals(events, finished))
        )

    met = 0
    for case in completed:
        if case.get("met_resolution_target") is True:
            met += 1
    turnaround: list[int] = []
    for approval in approvals:
        decided = _parse(approval.get("decided_at"))
        requested = _parse(approval.get("requested_at"))
        if requested and decided and _in_window(decided, start, end):
            turnaround.append(business_minutes_between(requested, decided, calendar))

    runs = [
        run
        for run in integrations
        if _in_window(_parse(run["started_at"]), start, end) and run["outcome"] in {"succeeded", "failed"}
    ]
    succeeded = sum(1 for run in runs if run["outcome"] == "succeeded")
    failed = sum(1 for run in runs if run["outcome"] == "failed")
    cloud_runs = [
        run
        for run in integrations
        if run["source"] == "power_automate" and _in_window(_parse(run["started_at"]), start, end)
    ]
    escalated_case_ids = {
        row["case_id"]
        for row in escalations
        if row["case_id"] in {case["id"] for case in received}
    }
    reopened = sum(
        1
        for events in events_by_case.values()
        for event in events
        if event["action"] == "case_reopened" and _in_window(_parse(event["occurred_at"]), start, end)
    )

    wait_by_department: dict[str, int] = {}
    for case in cases:
        department = case.get("owning_department") or case.get("requester_department") or "Unassigned"
        for interval_start, interval_end in _approval_intervals(events_by_case.get(case["id"], [])):
            overlap_start = max(interval_start, start)
            overlap_end = min(interval_end, end)
            if overlap_end > overlap_start:
                minutes = business_minutes_between(overlap_start, overlap_end, calendar)
                wait_by_department[department] = wait_by_department.get(department, 0) + minutes
    total_wait = sum(wait_by_department.values())
    bottleneck = None
    if total_wait > 0:
        department, minutes = max(wait_by_department.items(), key=lambda item: item[1])
        share = round((minutes / total_wait) * 100)
        bottleneck = {
            "department": department,
            "waiting_business_minutes": minutes,
            "share_of_approval_wait": share / 100,
            "statement": (
                f"{department} approvals accounted for {share}% of recorded waiting time in the selected period."
            ),
        }

    def tally(key: str) -> list[dict]:
        counts: dict[str, int] = {}
        for case in received:
            label = case.get(key) or "Unspecified"
            counts[label] = counts.get(label, 0) + 1
        return [{"label": label, "count": count} for label, count in sorted(counts.items())]

    ageing = {"0_1_days": 0, "2_3_days": 0, "4_7_days": 0, "8_plus_days": 0}
    for case in cases:
        if case["status"] not in OPEN_STATUSES:
            continue
        submitted = datetime.fromisoformat(case["submitted_at"])
        days = (end - submitted).total_seconds() / 86400
        if days < 2:
            ageing["0_1_days"] += 1
        elif days < 4:
            ageing["2_3_days"] += 1
        elif days < 8:
            ageing["4_7_days"] += 1
        else:
            ageing["8_plus_days"] += 1

    failure_counts: dict[str, int] = {}
    for run in runs:
        if run["outcome"] == "failed":
            code = run.get("error_code") or "unspecified"
            failure_counts[code] = failure_counts.get(code, 0) + 1

    notes = [
        "Measures are computed when this response is built.",
        "Business minutes use the Europe/London calendar configured for Northstar, including the listed holidays.",
        "Duplicate intake suppressions are not counted as failures.",
    ]
    if not cloud_runs:
        notes.append("No Power Automate run records are present in this window.")

    return {
        "window": {"from": start.isoformat(), "to": end.isoformat(), "timezone": calendar.timezone},
        "freshness": "computed_on_read",
        "definitions": DEFINITIONS,
        "metrics": {
            "received": len(received),
            "completed": len(completed),
            "avg_first_response_business_minutes": _mean(first_response_samples),
            "avg_resolution_business_minutes": _mean(resolution_samples),
            "sla_compliance_rate": _rate(met, len(completed)),
            "avg_approval_turnaround_business_minutes": _mean(turnaround),
            "recorded_integration_success_rate": _rate(succeeded, succeeded + failed),
            "escalation_rate": _rate(len(escalated_case_ids), len(received)),
            "reopened": reopened,
            "recorded_integration_failure_rate": _rate(failed, succeeded + failed),
        },
        "by_category": tally("category_id"),
        "by_department": tally("requester_department"),
        "approval_wait_by_department": [
            {"department": department, "business_minutes": minutes}
            for department, minutes in sorted(wait_by_department.items())
        ],
        "ageing_open_cases_calendar_days": ageing,
        "failure_causes": [
            {"error_code": code, "count": count} for code, count in sorted(failure_counts.items())
        ],
        "bottleneck": bottleneck,
        "power_automate_runs_in_window": len(cloud_runs),
        "notes": notes,
    }


def default_window(now: datetime) -> tuple[datetime, datetime]:
    from datetime import timedelta

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now - timedelta(days=90), now
