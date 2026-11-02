"""Server-side visibility. Knowing a case number is not authorisation."""

from __future__ import annotations

from dataclasses import dataclass

MUTATING_ROLES = {
    "employee",
    "service_desk_agent",
    "department_manager",
    "operations_manager",
    "administrator",
    "system",
}

AGENT_TEAMS_DEFAULT = (
    "IT Service Desk",
    "Manual Triage",
    "Unassigned",
    "Document Owners",
)


@dataclass(frozen=True)
class Principal:
    id: str
    display_name: str
    role: str
    department: str
    teams: tuple[str, ...]
    upn: str


def can_read(actor: Principal, case: dict, approvals: list[dict]) -> bool:
    if actor.role in {"operations_manager", "administrator", "auditor", "system"}:
        return True
    if actor.role == "employee":
        return case["requester_id"] == actor.id
    if actor.role == "service_desk_agent":
        team = case.get("assigned_team")
        if case.get("assigned_agent_id") == actor.id:
            return True
        if team is None:
            return True
        return team in actor.teams or team == "Unassigned"
    if actor.role == "department_manager":
        if case["requester_department"] == actor.department:
            return True
        if case.get("owning_department") == actor.department:
            return True
        return any(row.get("approver_id") == actor.id for row in approvals)
    return False


def can_accept(actor: Principal, case: dict) -> bool:
    if actor.role in {"administrator", "operations_manager", "system"}:
        return True
    team = case.get("assigned_team")
    if actor.role == "service_desk_agent":
        return team in actor.teams
    if actor.role == "department_manager":
        return case.get("owning_department") == actor.department
    return False


def sees_internal_comments(actor: Principal) -> bool:
    return actor.role in {
        "service_desk_agent",
        "department_manager",
        "operations_manager",
        "administrator",
        "auditor",
        "system",
    }
