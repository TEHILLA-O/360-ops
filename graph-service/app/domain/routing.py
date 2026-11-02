"""Configurable routing rules. Versioned. Never invents an employee."""

from __future__ import annotations

from dataclasses import dataclass

RULE_VERSION = "2026.11.0"

TEAM_DEPARTMENT = {
    "Finance Approval Queue": "Finance",
    "Sales Approval Queue": "Sales",
    "Human Resources Approval Queue": "Human Resources",
    "IT Approval Queue": "IT",
    "Operations Approval Queue": "Operations",
    "Facilities Approval Queue": "Facilities",
    "IT Service Desk": "IT",
    "Facilities Team": "Facilities",
    "Operations Scheduling": "Operations",
    "Service Operations": "Operations",
    "Manual Triage": "Operations",
    "Document Owners": "Operations",
    "Unassigned": None,
}


@dataclass(frozen=True)
class RoutingDecision:
    rule_id: str
    rule_version: str
    team: str | None
    owning_department: str | None
    reason: str
    outcome: str


def route_case(
    *,
    category_id: str | None,
    requester_department: str,
    manual_triage: bool,
    missing_information: bool,
) -> RoutingDecision:
    if manual_triage or missing_information or not category_id:
        return RoutingDecision(
            rule_id="TRIAGE-01",
            rule_version=RULE_VERSION,
            team="Manual Triage",
            owning_department="Operations",
            reason="The case needs a person because category, confidence, or required detail is incomplete.",
            outcome="assigned",
        )
    if category_id == "access_request":
        team = f"{requester_department} Approval Queue"
        if team not in TEAM_DEPARTMENT:
            return RoutingDecision(
                rule_id="ACCESS-UNROUTED",
                rule_version=RULE_VERSION,
                team=None,
                owning_department=None,
                reason=f"No approval queue is configured for {requester_department}.",
                outcome="failed",
            )
        rule = "ACCESS-FIN-01" if requester_department == "Finance" else "ACCESS-DEPT-01"
        return RoutingDecision(
            rule_id=rule,
            rule_version=RULE_VERSION,
            team=team,
            owning_department=requester_department,
            reason=f"Access requests for {requester_department} use that department's approval queue.",
            outcome="assigned",
        )
    table = {
        "it_support": ("IT-01", "IT Service Desk", "IT", "IT support is owned by the IT Service Desk."),
        "facilities_request": (
            "FAC-01",
            "Facilities Team",
            "Facilities",
            "Facilities requests are owned by the Facilities team.",
        ),
        "document_request": (
            "DOC-01",
            "Document Owners",
            requester_department,
            "Document requests go to the document owner queue.",
        ),
        "scheduling_request": (
            "SCH-01",
            "Operations Scheduling",
            "Operations",
            "Scheduling requests go to operations scheduling.",
        ),
        "general_service": (
            "GEN-01",
            "Service Operations",
            "Operations",
            "General requests go to service operations.",
        ),
    }
    if category_id not in table:
        return RoutingDecision(
            rule_id="UNASSIGNED-01",
            rule_version=RULE_VERSION,
            team=None,
            owning_department=None,
            reason="No routing rule matched this category.",
            outcome="failed",
        )
    rule_id, team, department, reason = table[category_id]
    return RoutingDecision(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        team=team,
        owning_department=department,
        reason=reason,
        outcome="assigned",
    )
