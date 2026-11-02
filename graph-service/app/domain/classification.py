"""Deterministic request classification.

This is the local policy classifier used when Copilot Studio is not connected.
Ambiguous text stays in manual triage. It does not invent a confident category.
Mandatory approval floors are applied by the workflow engine, not by this score.
"""

from __future__ import annotations

from dataclasses import dataclass

KEYWORDS: dict[str, tuple[str, ...]] = {
    "access_request": ("access", "permission", "permissions", "folder", "sharepoint", "team membership"),
    "it_support": (
        "laptop",
        "software",
        "password",
        "vpn",
        "outlook",
        "install",
        "crash",
        "device",
        "login",
        "account locked",
        "locked out",
    ),
    "document_request": ("policy", "handbook", "document", "pdf", "template", "form"),
    "scheduling_request": (
        "schedule",
        "meeting",
        "book",
        "onboarding",
        "appointment",
        "calendar",
        "collection",
    ),
    "facilities_request": (
        "hvac",
        "heating",
        "leak",
        "desk",
        "maintenance",
        "workspace",
        "furniture",
        "lights",
    ),
}

URGENT_PHRASES = (
    "compromised",
    "compromise",
    "phishing",
    "account takeover",
    "payroll down",
    "cannot log in",
    "can't log in",
    "locked out",
)


@dataclass(frozen=True)
class Classification:
    category_id: str | None
    priority: str
    missing_information: tuple[str, ...]
    confidence: str
    proposed_assignment_group: str | None
    policy_reason: str
    manual_triage: bool
    security_escalation: bool
    signals: tuple[str, ...]


def _hits(blob: str) -> list[str]:
    found = []
    for category_id, words in KEYWORDS.items():
        if any(word in blob for word in words):
            found.append(category_id)
    return found


def classify_text(subject: str, body: str) -> Classification:
    blob = f"{subject}\n{body}".strip().lower()
    security = any(phrase in blob for phrase in URGENT_PHRASES)
    priority = "urgent" if security else "normal"
    if len(blob) < 20:
        return Classification(
            category_id=None,
            priority=priority,
            missing_information=(
                "Describe what you need, which system or place is involved, and the business reason.",
            ),
            confidence="low",
            proposed_assignment_group="Manual Triage",
            policy_reason="The request does not contain enough detail to choose a category.",
            manual_triage=True,
            security_escalation=security,
            signals=("short_text",),
        )
    hits = _hits(blob)
    if len(hits) > 1:
        listed = ", ".join(hits)
        return Classification(
            category_id=None,
            priority=priority,
            missing_information=(),
            confidence="low",
            proposed_assignment_group="Manual Triage",
            policy_reason=f"The text matches more than one category ({listed}). A person must choose.",
            manual_triage=True,
            security_escalation=security,
            signals=tuple(hits),
        )
    if len(hits) == 1:
        category_id = hits[0]
        return Classification(
            category_id=category_id,
            priority=priority,
            missing_information=(),
            confidence="high",
            proposed_assignment_group=None,
            policy_reason=f"Matched the {category_id} keyword rule.",
            manual_triage=False,
            security_escalation=security,
            signals=(category_id,),
        )
    return Classification(
        category_id="general_service",
        priority=priority,
        missing_information=(),
        confidence="low",
        proposed_assignment_group="Manual Triage",
        policy_reason="No category keyword matched. The case stays in manual triage.",
        manual_triage=True,
        security_escalation=security,
        signals=("no_keyword",),
    )


def missing_required_fields(category: dict | None, case: dict) -> list[str]:
    if not category:
        return []
    missing: list[str] = []
    required = category["required_fields"]
    description = (case.get("description") or "").strip()
    if "description" in required and len(description) < 20:
        missing.append("Add a description of at least a few sentences.")
    if "resource_name" in required and not (case.get("resource_name") or "").strip():
        missing.append("Name the folder, team, or system you need access to.")
    if "justification" in required and not (case.get("justification") or "").strip():
        missing.append("Add the business reason for the request.")
    if "preferred_window" in required and not (case.get("preferred_window") or "").strip():
        missing.append("Give a preferred day or time window for the appointment.")
    return missing


def extract_structured_fields(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    labels = {
        "resource:": "resource_name",
        "justification:": "justification",
        "reason:": "justification",
        "window:": "preferred_window",
    }
    for line in text.splitlines():
        lowered = line.strip().lower()
        for label, field in labels.items():
            if lowered.startswith(label):
                value = line.split(":", 1)[1].strip()
                if value and field not in found:
                    found[field] = value
    return found
