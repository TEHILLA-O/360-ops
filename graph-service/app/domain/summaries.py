"""Requester-facing sentences built only from stored fields."""

from __future__ import annotations


def status_sentence(case: dict, category_name: str | None) -> str:
    """A short status line. Callers must pass the stored case, not a guessed state."""
    title = case["title"].rstrip(".")
    status = case["status"]
    approval = case["approval_state"]
    team = case.get("assigned_team") or "the assigned team"
    subject = title[0].lower() + title[1:] if title else "request"

    if status == "awaiting_information":
        return f"Your {subject} is waiting for more information before it can proceed."
    if approval == "rejected" or status == "rejected":
        return f"Your {subject} was rejected. No fulfilment task was created."
    if approval == "approved" and status == "awaiting_fulfilment":
        return (
            f"Your {subject} is approved and is awaiting fulfilment by the {team}."
        )
    if approval == "pending" or status == "awaiting_approval":
        return f"Your {subject} is waiting for a manager decision."
    if status == "in_progress":
        return f"Your {subject} is in progress with the {team}."
    if status == "assigned":
        return f"Your {subject} has been routed to the {team} and is not yet in progress."
    if status == "resolved":
        return f"Your {subject} is resolved."
    if status == "closed":
        return f"Your {subject} is closed."
    if status == "cancelled":
        return f"Your {subject} was cancelled."
    if status == "new":
        return f"Your {subject} has been received and has not been classified yet."
    label = category_name or "request"
    return f"Your {label} case {case['case_number']} is {status.replace('_', ' ')}."


def next_action(case: dict) -> str:
    if case["status"] == "awaiting_information":
        return "Reply with the missing detail. The case stays paused until that arrives."
    if case["approval_state"] == "approved" and case["status"] == "awaiting_fulfilment":
        return (
            "An administrator records verified completion after the approved change. "
            "OpsPilot does not grant the access itself."
        )
    if case["approval_state"] == "pending":
        return "The assigned manager still needs to decide."
    if case["approval_state"] == "rejected":
        return "You can submit a new request if the requirement changes. This one will not be fulfilled."
    if case["status"] in {"resolved", "closed"}:
        return "No further action is recorded."
    if case.get("blocking_reason"):
        return "An integration step failed. The case is not complete."
    return "The owning team continues the case."
