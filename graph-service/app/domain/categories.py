"""Configurable category policy. The frontend reads this; it does not hard-code it."""

from __future__ import annotations

CATEGORIES: tuple[dict, ...] = (
    {
        "id": "access_request",
        "name": "Access Request",
        "description": "Request access to a folder, team, or application. Approval does not grant the access.",
        "required_fields": ["description", "resource_name", "justification"],
        "approval_policy": "required",
        "priority_floor": "high",
        "fulfilment_required": True,
        "sla": {"urgent": 240, "high": 480, "normal": 1140, "low": 2850},
        "first_response_minutes": {"urgent": 30, "high": 60, "normal": 240, "low": 480},
        "resolution_requirements": "An administrator performs the access change outside OpsPilot and records verified completion.",
    },
    {
        "id": "it_support",
        "name": "IT Support",
        "description": "Device, software, and account problems handled by the IT service desk.",
        "required_fields": ["description"],
        "approval_policy": "not_required",
        "priority_floor": "normal",
        "fulfilment_required": False,
        "sla": {"urgent": 240, "high": 480, "normal": 1140, "low": 2850},
        "first_response_minutes": {"urgent": 30, "high": 60, "normal": 240, "low": 480},
        "resolution_requirements": "The assigned agent records what was fixed or why it cannot be fixed.",
    },
    {
        "id": "document_request",
        "name": "Document Request",
        "description": "Request a policy, form, or shared file that the requester is allowed to receive.",
        "required_fields": ["description"],
        "approval_policy": "not_required",
        "priority_floor": "normal",
        "fulfilment_required": False,
        "sla": {"urgent": 240, "high": 480, "normal": 1140, "low": 2850},
        "first_response_minutes": {"urgent": 30, "high": 60, "normal": 240, "low": 480},
        "resolution_requirements": "The document owner records which approved document was provided.",
    },
    {
        "id": "scheduling_request",
        "name": "Scheduling Request",
        "description": "Book a support session, onboarding meeting, inspection, or equipment collection.",
        "required_fields": ["description", "preferred_window"],
        "approval_policy": "not_required",
        "priority_floor": "normal",
        "fulfilment_required": True,
        "sla": {"urgent": 240, "high": 480, "normal": 1140, "low": 2850},
        "first_response_minutes": {"urgent": 30, "high": 60, "normal": 240, "low": 480},
        "resolution_requirements": "A calendar event must exist in Microsoft Graph before the case can be resolved.",
    },
    {
        "id": "facilities_request",
        "name": "Facilities Request",
        "description": "Maintenance, equipment, and workspace issues.",
        "required_fields": ["description"],
        "approval_policy": "not_required",
        "priority_floor": "normal",
        "fulfilment_required": False,
        "sla": {"urgent": 240, "high": 480, "normal": 1140, "low": 2850},
        "first_response_minutes": {"urgent": 30, "high": 60, "normal": 240, "low": 480},
        "resolution_requirements": "Facilities records the work completed or the reason it remains open.",
    },
    {
        "id": "general_service",
        "name": "General Service Request",
        "description": "Requests that do not fit a defined category after a person has reviewed them.",
        "required_fields": ["description"],
        "approval_policy": "not_required",
        "priority_floor": "low",
        "fulfilment_required": False,
        "sla": {"urgent": 240, "high": 480, "normal": 1140, "low": 2850},
        "first_response_minutes": {"urgent": 30, "high": 60, "normal": 240, "low": 480},
        "resolution_requirements": "Service operations records the outcome.",
    },
)


def category_map() -> dict[str, dict]:
    return {item["id"]: item for item in CATEGORIES}
