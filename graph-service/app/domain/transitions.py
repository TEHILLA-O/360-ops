"""Legal case status transitions. Approval state is tracked separately."""

from __future__ import annotations

ALLOWED: dict[str, set[str]] = {
    "new": {"awaiting_information", "classified", "cancelled"},
    "awaiting_information": {"classified", "cancelled"},
    "classified": {"assigned", "awaiting_information", "cancelled"},
    "assigned": {"awaiting_approval", "in_progress", "awaiting_fulfilment", "awaiting_information", "cancelled"},
    "awaiting_approval": {"approved", "rejected", "awaiting_information", "cancelled"},
    "approved": {"awaiting_fulfilment", "in_progress", "cancelled"},
    "rejected": {"closed", "awaiting_information"},
    "in_progress": {"awaiting_fulfilment", "resolved", "awaiting_information", "cancelled"},
    "awaiting_fulfilment": {"in_progress", "resolved", "cancelled"},
    "resolved": {"closed", "in_progress"},
    "closed": {"in_progress"},
    "cancelled": set(),
}

STATUSES = tuple(ALLOWED.keys())

APPROVAL_STATES = (
    "not_required",
    "pending",
    "approved",
    "rejected",
    "cancelled",
    "expired",
    "failed",
)


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED.get(current, set())
