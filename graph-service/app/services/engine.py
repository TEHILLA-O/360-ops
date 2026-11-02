"""Local policy engine.

This is the testable counterpart of the Power Automate specifications.
It is not a cloud flow, and its integration rows use source `local_policy_engine`
or `graph`. A row is marked `power_automate` only when a signed callback arrives.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.auth.graph_client import GraphClient
from app.clock import Clock
from app.config import Settings
from app.domain.calendar import DEFAULT_CALENDAR, BusinessCalendar
from app.domain.catalogue import FLOWS, LOCAL_FLOW_NAMES
from app.domain.categories import category_map
from app.domain.classification import (
    classify_text,
    extract_structured_fields,
    missing_required_fields,
)
from app.domain.permissions import Principal, can_accept, can_read, sees_internal_comments
from app.domain.routing import TEAM_DEPARTMENT, route_case
from app.domain.sla import add_business_minutes, evaluate_sla, higher_priority
from app.domain.summaries import next_action, status_sentence
from app.domain.transitions import can_transition
from app.errors import OpsError
from app.services.analytics import build_analytics, default_window
from app.store.db import Store, new_id

CASE_NUMBER_RE = re.compile(r"NS-\d+")
STOPWORDS = {
    "what",
    "whats",
    "happening",
    "with",
    "request",
    "please",
    "status",
    "about",
    "this",
    "that",
    "from",
    "have",
    "need",
    "your",
    "mine",
    "open",
    "case",
}

SYSTEM = Principal(
    id="policy.engine",
    display_name="OpsPilot policy engine",
    role="system",
    department="Operations",
    teams=tuple(TEAM_DEPARTMENT),
    upn="policy.engine@northstar.example",
)


def clean_text(value: str, max_len: int, *, allow_empty: bool = False) -> str:
    cleaned = "".join(ch for ch in value if ch in "\n\t" or ord(ch) >= 32).strip()
    if not cleaned and not allow_empty:
        raise OpsError("invalid_request", "Text is required.")
    if len(cleaned) > max_len:
        raise OpsError("invalid_request", "Text is too long.")
    return cleaned


class Engine:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        clock: Clock,
        graph: GraphClient,
        calendar: BusinessCalendar | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.clock = clock
        self.graph = graph
        self.calendar = calendar or DEFAULT_CALENDAR
        self.categories = category_map()

    def principal_from_header(self, actor_id: str | None) -> Principal:
        if self.settings.auth_mode != "local_synthetic":
            raise OpsError(
                "entra_session_required",
                "Local persona headers are disabled when Entra authentication is selected.",
                401,
            )
        if not actor_id or actor_id in {SYSTEM.id, "system.seed"}:
            raise OpsError("unauthenticated", "Choose a Northstar persona for this local session.", 401)
        person = self.store.get_requester(actor_id)
        if not person:
            raise OpsError("unauthenticated", "That persona is not in the local directory.", 401)
        return self._principal(person)

    def list_personas(self) -> list[dict]:
        if self.settings.auth_mode != "local_synthetic":
            return []
        return [
            {
                "id": person["id"],
                "display_name": person["display_name"],
                "role": person["role"],
                "department": person["department"],
                "job_title": person["job_title"],
                "identity_source": "local_synthetic_directory",
            }
            for person in self.store.list_requesters()
        ]

    def submit_web(
        self,
        actor: Principal,
        *,
        title: str,
        description: str,
        resource_name: str | None,
        justification: str | None,
        preferred_window: str | None,
        correlation_id: str,
    ) -> dict:
        if actor.role == "auditor":
            raise OpsError("forbidden", "Auditors cannot open cases.", 403)
        moment = self.clock.now()
        with self.store.session() as conn:
            case = self._insert_case(
                conn,
                title=clean_text(title, 140),
                description=clean_text(description, 4000),
                requester_id=actor.id,
                department=actor.department,
                source_channel="web",
                source_message_id=None,
                source_mailbox=None,
                dedup_key=None,
                submitted_at=moment,
                correlation_id=correlation_id,
                resource_name=clean_text(resource_name, 180, allow_empty=True) if resource_name else None,
                justification=clean_text(justification, 1000, allow_empty=True) if justification else None,
                preferred_window=clean_text(preferred_window, 180, allow_empty=True) if preferred_window else None,
                explicit_number=None,
            )
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=actor.id,
                action="request_received",
                at=moment,
                source="web_form",
                new_state="new",
                reason="Submitted from the OpsPilot form.",
                correlation_id=correlation_id,
                metadata={"channel": "web"},
            )
            self._acknowledge(conn, case, moment)
            case = self._classify_and_route(conn, case, correlation_id, moment + timedelta(seconds=1))
            case = self._maybe_request_approval(conn, case, correlation_id, moment + timedelta(seconds=2))
        return self._tool_envelope(self._must(case["id"]), actor)

    def ingest_message(
        self,
        actor: Principal,
        message: dict,
        *,
        process: bool,
        correlation_id: str,
        at: datetime | None = None,
        explicit_number: str | None = None,
    ) -> dict:
        self._require(actor, {"administrator", "operations_manager", "system"})
        moment = at or self.clock.now()
        mailbox = clean_text(message["mailbox"], 200).lower()
        message_id = clean_text(message["message_id"], 300)
        subject = clean_text(message["subject"], 300)
        body = clean_text(message.get("body") or "", 4000, allow_empty=True)
        sender = clean_text(message["sender_upn"], 200).lower()
        with self.store.session() as conn:
            if mailbox != self.settings.support_mailbox.lower():
                self._run(
                    conn,
                    flow_id="OPS-01",
                    operation="intake.message",
                    correlation_id=correlation_id,
                    case_id=None,
                    at=moment,
                    outcome="failed",
                    error_category="non_retryable",
                    error_code="wrong_mailbox",
                    message="The message mailbox does not match the configured support mailbox.",
                )
                raise OpsError("wrong_mailbox", "The message is not from the configured support mailbox.", 422)
            if _auto_reply(subject, message.get("headers") or {}):
                self._run(
                    conn,
                    flow_id="OPS-01",
                    operation="intake.message",
                    correlation_id=correlation_id,
                    case_id=None,
                    at=moment,
                    outcome="suppressed",
                    error_category=None,
                    error_code="auto_reply",
                    message="Automatic replies are ignored.",
                )
                return {"outcome": "suppressed", "reason": "auto_reply", "case_id": None}
            requester = self.store.get_requester_by_upn(sender)
            if not requester:
                self._audit(
                    conn,
                    case_id=None,
                    actor_id=actor.id,
                    action="request_received",
                    at=moment,
                    source="local_policy_engine",
                    reason="The sender is not in the local directory, so no case was created.",
                    correlation_id=correlation_id,
                    metadata={"sender_known": False},
                )
                self._run(
                    conn,
                    flow_id="OPS-01",
                    operation="intake.message",
                    correlation_id=correlation_id,
                    case_id=None,
                    at=moment,
                    outcome="failed",
                    error_category="human_action",
                    error_code="unknown_requester",
                    message="No directory record matches the sender.",
                )
                raise OpsError("unknown_requester", "The sender is not in the directory. No case was created.", 422)
            match = CASE_NUMBER_RE.search(subject)
            if match:
                existing = self.store.get_request_by_number(match.group(0))
                if existing and existing["requester_id"] != requester["id"]:
                    self._audit(
                        conn,
                        case_id=existing["id"],
                        actor_id=requester["id"],
                        action="access_denied",
                        at=moment,
                        source="local_policy_engine",
                        reason="A reply quoted a case number owned by someone else. The body was not attached.",
                        correlation_id=correlation_id,
                        metadata={"case_number": existing["case_number"]},
                    )
                    self._run(
                        conn,
                        flow_id="OPS-01",
                        operation="intake.thread",
                        correlation_id=correlation_id,
                        case_id=existing["id"],
                        at=moment,
                        outcome="failed",
                        error_category="security_sensitive",
                        error_code="cross_requester_thread",
                        message="The reply was not attached to another person's case.",
                    )
                    raise OpsError("not_found", "Case not found.", 404)
                if existing and existing["requester_id"] == requester["id"]:
                    self._communication(
                        conn,
                        case_id=existing["id"],
                        channel="outlook",
                        direction="inbound",
                        template="thread_update",
                        body=body[:500] or "Reply received.",
                        status="recorded",
                        at=moment,
                        recipient=requester["upn"],
                    )
                    self._journal(
                        conn,
                        case_id=existing["id"],
                        actor_id=requester["id"],
                        action="thread_appended",
                        at=moment,
                        source="local_policy_engine",
                        reason="A reply was correlated to the existing case.",
                        correlation_id=correlation_id,
                        metadata={"body_characters": len(body), "message_id": message_id},
                    )
                    self._run(
                        conn,
                        flow_id="OPS-01",
                        operation="intake.thread",
                        correlation_id=correlation_id,
                        case_id=existing["id"],
                        at=moment,
                        outcome="suppressed",
                        error_code="thread_appended",
                        message="Reply appended. No new case was created.",
                    )
                    return {"outcome": "thread_appended", "case_id": existing["id"], "case_number": existing["case_number"]}
            dedup = f"{mailbox}|{message_id}"
            duplicate = self.store.get_request_by_dedup(dedup)
            if duplicate:
                self._run(
                    conn,
                    flow_id="OPS-01",
                    operation="intake.message",
                    correlation_id=correlation_id,
                    case_id=duplicate["id"],
                    at=moment,
                    outcome="suppressed",
                    error_code="duplicate_message",
                    message="The provider message id was already ingested.",
                )
                self._journal(
                    conn,
                    case_id=duplicate["id"],
                    actor_id=SYSTEM.id,
                    action="duplicate_suppressed",
                    at=moment,
                    source="local_policy_engine",
                    reason="Repeated Outlook trigger ignored.",
                    correlation_id=correlation_id,
                    metadata={"message_id": message_id},
                )
                return {"outcome": "duplicate", "case_id": duplicate["id"], "case_number": duplicate["case_number"]}
            extracted = extract_structured_fields(body)
            case = self._insert_case(
                conn,
                title=subject,
                description=body or subject,
                requester_id=requester["id"],
                department=requester["department"],
                source_channel="outlook",
                source_message_id=message_id,
                source_mailbox=mailbox,
                dedup_key=dedup,
                submitted_at=moment,
                correlation_id=correlation_id,
                resource_name=extracted.get("resource_name"),
                justification=extracted.get("justification"),
                preferred_window=extracted.get("preferred_window"),
                explicit_number=explicit_number,
            )
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=SYSTEM.id,
                action="request_received",
                at=moment,
                source="local_policy_engine",
                new_state="new",
                reason="Outlook intake created the case.",
                correlation_id=correlation_id,
                metadata={"message_id": message_id, "body_characters": len(body)},
            )
            self._acknowledge(conn, case, moment)
            self._run(
                conn,
                flow_id="OPS-01",
                operation="intake.message",
                correlation_id=correlation_id,
                case_id=case["id"],
                at=moment,
                outcome="succeeded",
                message="Case created from the inbound message.",
            )
            if process:
                case = self._classify_and_route(conn, case, correlation_id, moment + timedelta(seconds=1))
                case = self._maybe_request_approval(conn, case, correlation_id, moment + timedelta(seconds=2))
        return {"outcome": "created", "case_id": case["id"], "case_number": case["case_number"]}

    def classify_manual(
        self,
        actor: Principal,
        case_id: str,
        category_id: str,
        reason: str,
        correlation_id: str,
    ) -> dict:
        self._require(actor, {"service_desk_agent", "operations_manager", "administrator", "system"})
        if category_id not in self.categories:
            raise OpsError("invalid_category", "That category is not configured.", 422)
        reason = clean_text(reason, 500)
        case = self._case_for(actor, case_id)
        moment = self.clock.now()
        with self.store.session() as conn:
            case = self._classify_and_route(
                conn,
                case,
                correlation_id,
                moment,
                manual_category=category_id,
                manual_reason=reason,
                actor_id=actor.id,
            )
            case = self._maybe_request_approval(conn, case, correlation_id, moment + timedelta(seconds=1))
        return self.present(self._must(case_id), actor, detail=True)

    def submit_clarification(self, actor: Principal, case_id: str, text: str, correlation_id: str) -> dict:
        text = clean_text(text, 2000)
        case = self._case_for(actor, case_id)
        if actor.role == "employee" and case["requester_id"] != actor.id:
            raise OpsError("not_found", "Case not found.", 404)
        if case["status"] not in {"awaiting_information", "new", "assigned", "classified"}:
            raise OpsError("invalid_transition", "This case is not accepting clarification.", 409)
        moment = self.clock.now()
        with self.store.session() as conn:
            description = f"{case['description']}\n\nClarification:\n{text}".strip()
            extracted = extract_structured_fields(text)
            fields = {
                "description": description[:4000],
                "resource_name": extracted.get("resource_name") or case.get("resource_name"),
                "justification": extracted.get("justification") or case.get("justification"),
                "preferred_window": extracted.get("preferred_window") or case.get("preferred_window"),
            }
            self._update(conn, case, fields)
            self._communication(
                conn,
                case_id=case["id"],
                channel="web",
                direction="inbound",
                template="clarification",
                body=text,
                status="recorded",
                at=moment,
                recipient=case["requester_id"],
            )
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=actor.id,
                action="clarification_submitted",
                at=moment,
                source="local_policy_engine",
                reason="The requester supplied more information.",
                correlation_id=correlation_id,
                metadata={"body_characters": len(text)},
            )
            case = self._reload(case["id"])
            case = self._classify_and_route(conn, case, correlation_id, moment + timedelta(seconds=1))
            case = self._maybe_request_approval(conn, case, correlation_id, moment + timedelta(seconds=2))
        return self._tool_envelope(self._must(case_id), actor)

    def request_clarification(self, actor: Principal, case_id: str, question: str, correlation_id: str) -> dict:
        self._require(actor, {"service_desk_agent", "department_manager", "operations_manager", "administrator"})
        question = clean_text(question, 1000)
        case = self._case_for(actor, case_id)
        moment = self.clock.now()
        with self.store.session() as conn:
            if case["status"] != "awaiting_information":
                case = self._move(
                    conn,
                    case,
                    "awaiting_information",
                    actor.id,
                    question,
                    correlation_id,
                    moment,
                    action="clarification_requested",
                )
            else:
                self._journal(
                    conn,
                    case_id=case["id"],
                    actor_id=actor.id,
                    action="clarification_requested",
                    at=moment,
                    source="local_policy_engine",
                    previous_state=case["status"],
                    new_state=case["status"],
                    reason=question,
                    correlation_id=correlation_id,
                )
            self._communication(
                conn,
                case_id=case["id"],
                channel="outlook",
                direction="outbound",
                template="clarification_request",
                body=question,
                status="not_delivered_channel_unconfigured",
                at=moment,
                recipient=case["requester_id"],
            )
        return self.present(self._must(case_id), actor, detail=True)

    def accept_work(self, actor: Principal, case_id: str, correlation_id: str, at: datetime | None = None) -> dict:
        case = self._case_for(actor, case_id)
        if case["status"] not in {"assigned", "in_progress", "awaiting_fulfilment", "approved"}:
            raise OpsError("invalid_transition", "This case cannot be accepted in its current state.", 409)
        if not can_accept(actor, case):
            raise OpsError("forbidden", "You cannot take this case.", 403)
        team = case.get("assigned_team") or ""
        if team.endswith("Approval Queue"):
            raise OpsError("invalid_transition", "Approval queues are decided with the approval action.", 409)
        if case.get("assigned_agent_id") and case["assigned_agent_id"] != actor.id and actor.role == "service_desk_agent":
            raise OpsError("already_assigned", "Another agent already owns this case.", 409)
        moment = at or self.clock.now()
        with self.store.session() as conn:
            self._update(conn, case, {"assigned_agent_id": actor.id})
            self._assignment(
                conn,
                case,
                team=case.get("assigned_team"),
                agent_id=actor.id,
                rule_id="ACCEPT-01",
                reason=f"{actor.display_name} accepted the case.",
                outcome="assigned",
                actor_id=actor.id,
                at=moment,
            )
            category = self.categories.get(case.get("category_id") or "")
            target = None
            if case["status"] == "assigned" and case["approval_state"] in {"not_required", "approved"}:
                if category and category["id"] == "scheduling_request":
                    target = "awaiting_fulfilment"
                elif category and category["fulfilment_required"] and case["approval_state"] == "approved":
                    target = "awaiting_fulfilment"
                else:
                    target = "in_progress"
            if target:
                case = self._reload(case["id"])
                case = self._move(
                    conn,
                    case,
                    target,
                    actor.id,
                    "Work accepted.",
                    correlation_id,
                    moment,
                    action="work_accepted",
                )
            else:
                self._journal(
                    conn,
                    case_id=case["id"],
                    actor_id=actor.id,
                    action="work_accepted",
                    at=moment,
                    source="local_policy_engine",
                    previous_state=case["status"],
                    new_state=case["status"],
                    reason="Owner recorded without a status change.",
                    correlation_id=correlation_id,
                )
        return self.present(self._must(case_id), actor, detail=True)

    def record_simulated_decision(
        self,
        actor: Principal,
        approval_id: str,
        decision: str,
        comments: str,
        correlation_id: str,
        at: datetime | None = None,
    ) -> dict:
        if not self.settings.allow_local_approval_simulation and actor.role != "system":
            raise OpsError("simulation_disabled", "Local approval simulation is turned off.", 403)
        self._require(actor, {"administrator", "system"})
        if decision not in {"approved", "rejected"}:
            raise OpsError("invalid_request", "Decision must be approved or rejected.", 422)
        comments = clean_text(comments, 1000)
        approval = self.store.get_row("approvals", approval_id)
        if not approval:
            raise OpsError("not_found", "Approval not found.", 404)
        case = self._case_for(actor, approval["case_id"])
        if approval["approver_id"] == case["requester_id"]:
            raise OpsError("self_approval_blocked", "A requester cannot approve their own restricted request.", 403)
        moment = at or self.clock.now()
        with self.store.session() as conn:
            updated = self.store.update_approval(
                conn,
                approval_id,
                {
                    "state": decision,
                    "decided_at": moment.isoformat(),
                    "comments": comments,
                    "decision_authority": "local_simulation",
                    "recorded_by": actor.id,
                    "correlation_id": correlation_id,
                },
            )
            if updated != 1:
                raise OpsError("invalid_transition", "Only a pending approval can be decided, and only once.", 409)
            case = self._move(
                conn,
                case,
                decision,
                actor.id,
                comments,
                correlation_id,
                moment,
                action="approval_recorded",
                extra={"approval_state": decision},
            )
            self._run(
                conn,
                flow_id="OPS-04",
                operation="approval.decision",
                correlation_id=correlation_id,
                case_id=case["id"],
                at=moment,
                outcome="succeeded",
                message="Local simulation recorded the decision. Microsoft Approvals was not called.",
            )
            category = self.categories.get(case.get("category_id") or "")
            if decision == "approved" and category and category["fulfilment_required"]:
                team, department = _fulfilment_destination(category["id"], case)
                case = self._move(
                    conn,
                    case,
                    "awaiting_fulfilment",
                    SYSTEM.id,
                    "Approved work is waiting for a person to carry it out.",
                    correlation_id,
                    moment + timedelta(seconds=1),
                    action="fulfilment_opened",
                    extra={"assigned_team": team, "owning_department": department, "assigned_agent_id": None},
                )
                self._assignment(
                    conn,
                    case,
                    team=team,
                    agent_id=None,
                    rule_id="FULFIL-01",
                    reason="Approval created a fulfilment task. Access is not granted by this step.",
                    outcome="assigned",
                    actor_id=SYSTEM.id,
                    at=moment + timedelta(seconds=1),
                )
            if decision == "rejected":
                self._notify(
                    conn,
                    channel="outlook",
                    template="approval_rejected",
                    summary=f"{case['case_number']} was rejected. No fulfilment task was created.",
                    case_id=case["id"],
                    recipient=case["requester_id"],
                    at=moment,
                )
        return self.present(self._must(case["id"]), actor, detail=True)

    def record_power_automate_decision(
        self,
        *,
        approval_id: str,
        decision: str,
        comments: str,
        workflow_run_ref: str,
        correlation_id: str,
    ) -> dict:
        """Reserved for a signed Power Automate callback. Disabled until a run reference is real."""
        raise OpsError(
            "power_automate_not_connected",
            "No Power Automate approval callback is configured. The decision was not recorded.",
            503,
        )

    def record_fulfilment(
        self,
        actor: Principal,
        case_id: str,
        summary: str,
        correlation_id: str,
        at: datetime | None = None,
    ) -> dict:
        self._require(actor, {"administrator", "system"})
        summary = clean_text(summary, 1000)
        case = self._case_for(actor, case_id)
        category = self.categories.get(case.get("category_id") or "")
        if category and category["approval_policy"] == "required" and case["approval_state"] != "approved":
            raise OpsError(
                "fulfilment_blocked",
                "Fulfilment cannot start unless the required approval is approved.",
                409,
            )
        if category and category["id"] == "scheduling_request" and not case.get("calendar_event_id"):
            raise OpsError(
                "calendar_missing",
                "Scheduling cannot be resolved until Microsoft Graph returns an event id.",
                409,
            )
        moment = at or self.clock.now()
        with self.store.session() as conn:
            case = self._move(
                conn,
                case,
                "resolved",
                actor.id,
                summary,
                correlation_id,
                moment,
                action="case_resolved",
                extra={
                    "resolution_summary": summary,
                    "completed_at": moment.isoformat(),
                    "blocking_reason": None,
                },
                metadata={"access_granted_by_opspilot": False, "verified_completion": True},
            )
        return self.present(self._must(case_id), actor, detail=True)

    def resolve_case(
        self,
        actor: Principal,
        case_id: str,
        summary: str,
        correlation_id: str,
        at: datetime | None = None,
    ) -> dict:
        self._require(actor, {"service_desk_agent", "department_manager", "operations_manager", "administrator", "system"})
        case = self._case_for(actor, case_id)
        category = self.categories.get(case.get("category_id") or "")
        if category and category["approval_policy"] == "required":
            raise OpsError("fulfilment_blocked", "Approved access is completed by an administrator.", 403)
        if category and category["id"] == "scheduling_request" and not case.get("calendar_event_id"):
            raise OpsError("calendar_missing", "No Graph calendar event is stored on this case.", 409)
        if case["approval_state"] == "rejected":
            raise OpsError("fulfilment_blocked", "A rejected request cannot be fulfilled.", 409)
        summary = clean_text(summary, 1000)
        moment = at or self.clock.now()
        with self.store.session() as conn:
            case = self._move(
                conn,
                case,
                "resolved",
                actor.id,
                summary,
                correlation_id,
                moment,
                action="case_resolved",
                extra={"resolution_summary": summary, "completed_at": moment.isoformat()},
            )
        return self.present(self._must(case_id), actor, detail=True)

    def close_case(self, actor: Principal, case_id: str, reason: str, correlation_id: str, at: datetime | None = None) -> dict:
        self._require(actor, {"operations_manager", "administrator", "system"})
        case = self._case_for(actor, case_id)
        moment = at or self.clock.now()
        with self.store.session() as conn:
            self._move(conn, case, "closed", actor.id, clean_text(reason, 500), correlation_id, moment, action="case_closed")
        return self.present(self._must(case_id), actor, detail=True)

    def cancel_case(self, actor: Principal, case_id: str, reason: str, correlation_id: str, at: datetime | None = None) -> dict:
        case = self._case_for(actor, case_id)
        if actor.role == "employee" and case["requester_id"] != actor.id:
            raise OpsError("not_found", "Case not found.", 404)
        if actor.role == "employee" and case["status"] not in {"new", "awaiting_information"}:
            raise OpsError("forbidden", "Ask the service desk to cancel a case that is already in progress.", 403)
        if actor.role not in {"employee", "service_desk_agent", "operations_manager", "administrator", "system"}:
            raise OpsError("forbidden", "You cannot cancel this case.", 403)
        moment = at or self.clock.now()
        with self.store.session() as conn:
            self._move(
                conn,
                case,
                "cancelled",
                actor.id,
                clean_text(reason, 500),
                correlation_id,
                moment,
                action="case_cancelled",
                extra={"completed_at": moment.isoformat()},
            )
        return self.present(self._must(case_id), actor, detail=True)

    def reopen_case(self, actor: Principal, case_id: str, reason: str, correlation_id: str, at: datetime | None = None) -> dict:
        self._require(actor, {"service_desk_agent", "operations_manager", "administrator", "system"})
        case = self._case_for(actor, case_id)
        moment = at or self.clock.now()
        with self.store.session() as conn:
            self._move(
                conn,
                case,
                "in_progress",
                actor.id,
                clean_text(reason, 500),
                correlation_id,
                moment,
                action="case_reopened",
                extra={"completed_at": None},
            )
        return self.present(self._must(case_id), actor, detail=True)

    def add_document_reference(
        self,
        actor: Principal,
        case_id: str,
        *,
        filename: str,
        doc_type: str,
        source: str,
        correlation_id: str,
    ) -> dict:
        case = self._case_for(actor, case_id)
        if actor.role == "auditor":
            raise OpsError("forbidden", "Auditors cannot attach documents.", 403)
        moment = self.clock.now()
        row = {
            "id": new_id(),
            "case_id": case["id"],
            "filename": clean_text(filename, 180),
            "doc_type": clean_text(doc_type, 40),
            "source": source if source in {"manual_reference", "synthetic_seed"} else "manual_reference",
            "owner_id": actor.id,
            "uploaded_at": moment.isoformat(),
            "version_label": "1",
            "access_state": "reference_recorded",
            "review_state": "submitted",
            "sharepoint_item_id": None,
        }
        with self.store.session() as conn:
            self.store.insert_child(conn, "document_references", row)
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=actor.id,
                action="document_attached",
                at=moment,
                source="local_policy_engine",
                reason="A document reference was recorded. The file was not copied out of SharePoint.",
                correlation_id=correlation_id,
                metadata={"filename": row["filename"], "sharepoint_connected": False},
            )
        return row

    def schedule_appointment(
        self,
        actor: Principal,
        case_id: str,
        *,
        token: str | None,
        start: datetime,
        end: datetime,
        correlation_id: str,
        attempt: int = 1,
        predecessor_id: str | None = None,
    ) -> dict:
        self._require(actor, {"service_desk_agent", "operations_manager", "administrator", "system"})
        case = self._case_for(actor, case_id)
        if case.get("category_id") != "scheduling_request":
            raise OpsError("invalid_request", "Calendar scheduling applies to scheduling requests.", 422)
        if case.get("calendar_event_id"):
            return {
                "success": True,
                "created": False,
                "event_id": case["calendar_event_id"],
                "message": "A Graph event id is already stored. No second event was created.",
            }
        payload = {
            "subject": f"{case['case_number']} {case['title']}"[:140],
            "body": {
                "contentType": "Text",
                "content": f"OpsPilot case {case['case_number']}. The case record holds the request detail.",
            },
            "start": _graph_time(start),
            "end": _graph_time(end),
        }
        result = self.graph.create_event(token, payload)
        moment = self.clock.now()
        with self.store.session() as conn:
            if not result.ok or not (result.body or {}).get("id"):
                self._update(conn, case, {"blocking_reason": result.error_code or "graph_event_missing"})
                self._journal(
                    conn,
                    case_id=case["id"],
                    actor_id=actor.id,
                    action="calendar_event_failed",
                    at=moment,
                    source="graph",
                    reason=result.message,
                    correlation_id=correlation_id,
                    metadata=result.safe_metadata,
                )
                run_id = self._run(
                    conn,
                    flow_id="OPS-05",
                    operation="graph.create_event",
                    correlation_id=correlation_id,
                    case_id=case["id"],
                    at=moment,
                    outcome="failed",
                    error_category=result.error_category,
                    error_code=result.error_code,
                    message=result.message,
                    attempt=attempt,
                    predecessor_id=predecessor_id,
                    source="graph",
                )
                return {
                    "success": False,
                    "created": False,
                    "event_id": None,
                    "error_code": result.error_code,
                    "message": result.message,
                    "integration_id": run_id,
                }
            event_id = str(result.body["id"])
            self._update(conn, case, {"calendar_event_id": event_id, "blocking_reason": None})
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=actor.id,
                action="calendar_event_created",
                at=moment,
                source="graph",
                reason="Microsoft Graph returned an event id.",
                correlation_id=correlation_id,
                integration_ref=event_id,
                metadata={"operation": "graph.create_event"},
            )
            self._run(
                conn,
                flow_id="OPS-05",
                operation="graph.create_event",
                correlation_id=correlation_id,
                case_id=case["id"],
                at=moment,
                outcome="succeeded",
                message="Calendar event created on the signed-in user's calendar.",
                attempt=attempt,
                predecessor_id=predecessor_id,
                source="graph",
            )
        return {"success": True, "created": True, "event_id": event_id, "message": "Graph created the event."}

    def retry_integration(self, actor: Principal, run_id: str, token: str | None, correlation_id: str) -> dict:
        self._require(actor, {"administrator", "operations_manager"})
        run = self.store.get_row("integration_runs", run_id)
        if not run:
            raise OpsError("not_found", "Integration run not found.", 404)
        if run["outcome"] != "failed":
            raise OpsError("retry_not_supported", "Only a failed run can be retried.", 409)
        if run["error_category"] in {"non_retryable", "security_sensitive"}:
            raise OpsError("retry_not_supported", "This failure is not safe to repeat.", 409)
        if run["operation"] != "graph.create_event" or not run.get("case_id"):
            raise OpsError(
                "retry_not_supported",
                "This step has side effects that must be rerun explicitly, not repeated blindly.",
                409,
            )
        start = self.clock.now() + timedelta(hours=1)
        return self.schedule_appointment(
            actor,
            run["case_id"],
            token=token,
            start=start,
            end=start + timedelta(minutes=30),
            correlation_id=correlation_id,
            attempt=int(run["attempt"]) + 1,
            predecessor_id=run["id"],
        )

    def sweep_sla(self, actor: Principal) -> dict:
        self._require(actor, {"operations_manager", "administrator", "system"})
        created: list[str] = []
        moment = self.clock.now()
        correlation_id = str(uuid.uuid4())
        with self.store.session() as conn:
            for case in self.store.list_requests():
                if case["status"] in {"resolved", "closed", "cancelled"}:
                    continue
                sla = self._sla(case)
                self.store.insert_child(
                    conn,
                    "sla_snapshots",
                    {
                        "id": new_id(),
                        "case_id": case["id"],
                        "state": sla["state"],
                        "evaluated_at": moment.isoformat(),
                        "elapsed_business_minutes": sla["elapsed_business_minutes"],
                        "target_business_minutes": sla["target_business_minutes"],
                        "due_at": sla["due_at"],
                        "policy_version": self.calendar.policy_version,
                        "kind": "resolution",
                    },
                )
                if sla["state"] in {"breached", "approaching"}:
                    key = f"{case['id']}:resolution:{sla['state']}"
                    if self._escalation(conn, case, key, sla["state"], moment, correlation_id):
                        created.append(case["case_number"])
            self._run(
                conn,
                flow_id="OPS-06",
                operation="sla.sweep",
                correlation_id=correlation_id,
                case_id=None,
                at=moment,
                outcome="succeeded",
                message=f"Local SLA sweep recorded {len(created)} new escalation(s).",
            )
        return {"created_case_numbers": created, "source": "local_policy_engine", "flow_id": "OPS-06"}

    def enquire(self, actor: Principal, text: str) -> dict:
        visible = [case for case in self.store.list_requests() if self._readable(actor, case)]
        match = CASE_NUMBER_RE.search(text or "")
        if match:
            case = self.store.get_request_by_number(match.group(0))
            if not case or not self._readable(actor, case):
                if case:
                    with self.store.session() as conn:
                        self._audit(
                            conn,
                            case_id=case["id"],
                            actor_id=actor.id,
                            action="access_denied",
                            at=self.clock.now(),
                            source="assistant_tool",
                            reason="Status enquiry for a case the caller cannot view.",
                            correlation_id=str(uuid.uuid4()),
                            metadata={"case_number": case["case_number"]},
                        )
                return self._empty_tool(
                    "I can't find a request you are allowed to view.",
                    "no_match",
                )
            return self._tool_envelope(case, actor)
        terms = [
            word
            for word in re.findall(r"[a-z0-9]{4,}", (text or "").lower())
            if word not in STOPWORDS
        ]
        matches = []
        for case in visible:
            category = self.categories.get(case.get("category_id") or "")
            hay = " ".join(
                filter(
                    None,
                    [case["title"], case.get("category_id"), category["name"] if category else None, case["case_number"]],
                )
            ).lower()
            if terms and any(term in hay for term in terms):
                matches.append(case)
        active = [case for case in matches if case["status"] not in {"closed", "cancelled", "resolved"}]
        chosen = active or matches
        if not chosen:
            return self._empty_tool("I can't find an open request of yours that matches that description.", "no_match")
        if len(chosen) > 1:
            return {
                "success": True,
                "case_id": None,
                "case_number": None,
                "status": None,
                "message": "Several of your requests match. Ask about one case number.",
                "next_action": "Choose a case number.",
                "updated_at": self.clock.now().isoformat(),
                "error_code": "ambiguous",
                "candidates": [
                    {"case_number": case["case_number"], "title": case["title"], "status": case["status"]}
                    for case in chosen[:5]
                ],
            }
        return self._tool_envelope(chosen[0], actor)

    def my_open_requests(self, actor: Principal) -> dict:
        cases = [
            case
            for case in self.store.list_requests()
            if case["requester_id"] == actor.id and case["status"] not in {"closed", "cancelled", "resolved"}
        ]
        return {
            "success": True,
            "message": f"You have {len(cases)} open request(s).",
            "requests": [
                {
                    "case_id": case["id"],
                    "case_number": case["case_number"],
                    "title": case["title"],
                    "status": case["status"],
                    "approval_state": case["approval_state"],
                }
                for case in cases
            ],
            "error_code": None,
            "updated_at": self.clock.now().isoformat(),
        }

    def explain_approval(self, actor: Principal, case_id: str | None) -> dict:
        if not case_id:
            access = self.categories["access_request"]
            return {
                "success": True,
                "message": "Access requests require a manager decision. Approval does not grant the access.",
                "approval_policy": access["approval_policy"],
                "error_code": None,
            }
        case = self._case_for(actor, case_id)
        category = self.categories.get(case.get("category_id") or "")
        sentence = status_sentence(self._hydrate(case), category["name"] if category else None)
        return {
            "success": True,
            "case_number": case["case_number"],
            "approval_state": case["approval_state"],
            "message": sentence,
            "next_action": next_action(self._hydrate(case)),
            "approval_policy": category["approval_policy"] if category else None,
            "error_code": None,
        }

    def guidance(self, category_id: str | None) -> dict:
        if category_id and category_id not in self.categories:
            return {
                "success": False,
                "error_code": "unknown_category",
                "message": "That is not one of the configured request categories.",
            }
        chosen = [self.categories[category_id]] if category_id else list(self.categories.values())
        return {
            "success": True,
            "source": "local_approved_policy_copy",
            "copilot_studio_connected": False,
            "categories": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "description": item["description"],
                    "required_fields": item["required_fields"],
                    "approval_policy": item["approval_policy"],
                    "resolution_requirements": item["resolution_requirements"],
                }
                for item in chosen
            ],
            "error_code": None,
        }

    def escalate_question(self, actor: Principal, question: str, case_id: str | None) -> dict:
        question = clean_text(question, 1000)
        case = self._case_for(actor, case_id) if case_id else None
        moment = self.clock.now()
        with self.store.session() as conn:
            self._notify(
                conn,
                channel="teams",
                template="assistant_escalation",
                summary=f"{actor.display_name} asked the service desk: {question[:180]}",
                case_id=case["id"] if case else None,
                recipient="service-operations",
                at=moment,
            )
            self._audit(
                conn,
                case_id=case["id"] if case else None,
                actor_id=actor.id,
                action="assistant_escalated",
                at=moment,
                source="assistant_tool",
                reason=question,
                correlation_id=str(uuid.uuid4()),
            )
        return {
            "success": True,
            "message": "The question was recorded for the service desk. Teams was not called because no channel is configured.",
            "error_code": None,
            "delivery_status": "not_delivered_channel_unconfigured",
        }

    def list_visible(self, actor: Principal) -> list[dict]:
        return [self.present(case, actor) for case in self.store.list_requests() if self._readable(actor, case)]

    def present(self, case: dict, actor: Principal, *, detail: bool = False) -> dict:
        if not self._readable(actor, case):
            with self.store.session() as conn:
                self._audit(
                    conn,
                    case_id=case["id"],
                    actor_id=actor.id,
                    action="access_denied",
                    at=self.clock.now(),
                    source="api",
                    reason="The caller is not allowed to view this case.",
                    correlation_id=str(uuid.uuid4()),
                    metadata={"case_number": case["case_number"]},
                )
            raise OpsError("not_found", "Case not found.", 404)
        hydrated = self._hydrate(case)
        requester = self.store.get_requester(hydrated["requester_id"])
        agent = self.store.get_requester(hydrated["assigned_agent_id"]) if hydrated.get("assigned_agent_id") else None
        category = self.categories.get(hydrated.get("category_id") or "")
        events = self.store.list_where("case_events", "case_id", hydrated["id"])
        sla = self._sla(hydrated, events)
        approvals = self.store.list_where("approvals", "case_id", hydrated["id"])
        if not sees_internal_comments(actor):
            approvals = [{**row, "comments": None} for row in approvals]
        view = {
            "id": hydrated["id"],
            "case_number": hydrated["case_number"],
            "title": hydrated["title"],
            "status": hydrated["status"],
            "approval_state": hydrated["approval_state"],
            "priority": hydrated["priority"],
            "category_id": hydrated.get("category_id"),
            "category_name": category["name"] if category else None,
            "requester_department": hydrated["requester_department"],
            "owning_department": hydrated.get("owning_department"),
            "assigned_team": hydrated.get("assigned_team"),
            "assigned_agent_id": hydrated.get("assigned_agent_id"),
            "assigned_agent_name": agent["display_name"] if agent else None,
            "requester_id": hydrated["requester_id"],
            "requester_name": requester["display_name"] if requester else hydrated["requester_id"],
            "source_channel": hydrated["source_channel"],
            "submitted_at": hydrated["submitted_at"],
            "due_at": sla["due_at"],
            "completed_at": hydrated.get("completed_at"),
            "sla_state": sla["state"],
            "sla_elapsed_business_minutes": sla["elapsed_business_minutes"],
            "sla_target_business_minutes": sla["target_business_minutes"],
            "met_resolution_target": sla["met_resolution_target"],
            "manual_triage": hydrated["manual_triage"],
            "security_flag": hydrated["security_flag"],
            "blocking_reason": hydrated.get("blocking_reason"),
            "calendar_event_id": hydrated.get("calendar_event_id"),
            "version": hydrated["version"],
            "classification_confidence": hydrated.get("classification_confidence"),
            "classification_reason": hydrated.get("classification_reason"),
            "missing_information": hydrated["missing_information"],
            "decision_authorities": sorted({row["decision_authority"] for row in approvals}),
        }
        if detail:
            view["description"] = hydrated["description"]
            view["resource_name"] = hydrated.get("resource_name")
            view["justification"] = hydrated.get("justification")
            view["preferred_window"] = hydrated.get("preferred_window")
            view["resolution_summary"] = hydrated.get("resolution_summary")
            view["events"] = [_public_event(event) for event in events]
            view["approvals"] = _name_people(approvals, self.store)
            view["assignments"] = self.store.list_where("assignments", "case_id", hydrated["id"])
            view["communications"] = self.store.list_where("communications", "case_id", hydrated["id"])
            view["documents"] = self.store.list_where("document_references", "case_id", hydrated["id"])
            view["integrations"] = self.store.list_where("integration_runs", "case_id", hydrated["id"])
            view["escalations"] = self.store.list_where("escalations", "case_id", hydrated["id"])
            view["status_sentence"] = status_sentence(hydrated, category["name"] if category else None)
            view["next_action"] = next_action(hydrated)
        return view

    def attention(self, actor: Principal) -> list[dict]:
        items = []
        latest = self._latest_runs()
        for case in self.store.list_requests():
            if not self._readable(actor, case):
                continue
            if case["status"] in {"resolved", "closed", "cancelled"}:
                continue
            sla = self._sla(case)
            if case["priority"] == "urgent" or case.get("security_flag"):
                items.append(_attention("security" if case.get("security_flag") else "urgent", case, "Priority or security flag needs a person."))
            if case["status"] == "awaiting_approval":
                items.append(_attention("approval_blocking", case, "Work is waiting on a manager decision."))
            if case["approval_state"] == "failed":
                items.append(_attention("missing_approver", case, case.get("blocking_reason") or "No approver could be resolved."))
            if sla["state"] == "breached":
                items.append(_attention("sla_breach", case, "The resolution target has been passed."))
            elif sla["state"] == "approaching":
                items.append(_attention("sla_approaching", case, "The resolution target is inside the warning window."))
            if case.get("manual_triage"):
                items.append(_attention("manual_triage", case, "Classification was not confident."))
            if not case.get("assigned_team"):
                items.append(_attention("unassigned", case, "No team was assigned."))
        for run in latest.values():
            if run["outcome"] != "failed" or not run.get("case_id"):
                continue
            case = self.store.get_request(run["case_id"])
            if case and self._readable(actor, case) and case["status"] not in {"resolved", "closed", "cancelled"}:
                items.append(
                    _attention(
                        "integration_failure",
                        case,
                        f"{run['operation']} failed ({run.get('error_code')}). Source: {run['source']}.",
                    )
                )
        return items

    def command(self, actor: Principal) -> dict:
        visible = [case for case in self.store.list_requests() if self._readable(actor, case)]
        tz = ZoneInfo(self.calendar.timezone)
        today = self.clock.now().astimezone(tz).date()
        open_cases = [case for case in visible if case["status"] not in {"resolved", "closed", "cancelled"}]

        def _done_today(case: dict) -> bool:
            if not case.get("completed_at") or case["status"] not in {"resolved", "closed"}:
                return False
            return datetime.fromisoformat(case["completed_at"]).astimezone(tz).date() == today

        breaches = [case for case in open_cases if self._sla(case)["state"] == "breached"]
        stages = {
            "new": ["new"],
            "classification": ["classified", "awaiting_information"],
            "assignment": ["assigned"],
            "approval": ["awaiting_approval", "rejected"],
            "in_progress": ["in_progress", "approved"],
            "fulfilment": ["awaiting_fulfilment"],
            "resolution": ["resolved", "closed"],
        }
        return {
            "open_cases": len(open_cases),
            "awaiting_approval": sum(1 for case in visible if case["status"] == "awaiting_approval"),
            "sla_breaches": len(breaches),
            "completed_today": sum(1 for case in visible if _done_today(case)),
            "recorded_integration_failures": len(
                [run for run in self._latest_runs().values() if run["outcome"] == "failed"]
            ),
            "lifecycle": [
                {"stage": stage, "count": sum(1 for case in visible if case["status"] in statuses)}
                for stage, statuses in stages.items()
            ],
            "service_health": self.service_health(),
            "data_plane": "local_sqlite_case_store",
            "cloud_flows_deployed": False,
        }

    def service_health(self) -> dict:
        graph_state = "not_configured"
        if self.settings.entra_configured:
            graph_state = "authorisation_required"
        return {
            "case_store": "available",
            "outlook_connector": "not_configured",
            "power_automate": "not_configured",
            "copilot_studio": "not_configured",
            "dataverse": "not_configured",
            "sharepoint": "not_configured",
            "teams": "connected" if self.settings.teams_configured else "not_configured",
            "graph": graph_state,
        }

    def workflow_board(self) -> dict:
        runs = self.store.list_all("integration_runs")
        board = []
        for flow in FLOWS:
            local = [run for run in runs if run["flow_id"] == flow["id"] and run["source"] != "power_automate"]
            cloud = [run for run in runs if run["flow_id"] == flow["id"] and run["source"] == "power_automate"]
            last = max(local, key=lambda run: run["started_at"], default=None)
            board.append(
                {
                    **flow,
                    "observed_local_runs": len(local),
                    "observed_local_failures": sum(1 for run in local if run["outcome"] == "failed"),
                    "observed_cloud_runs": len(cloud),
                    "last_local_run_at": last["started_at"] if last else None,
                    "last_local_outcome": last["outcome"] if last else None,
                }
            )
        return {
            "flows": board,
            "note": (
                "observed_local_runs are the local policy engine or direct Graph calls. "
                "observed_cloud_runs counts signed Power Automate callbacks only. "
                "deployed is false because no cloud flow was created in a tenant."
            ),
        }

    def analytics(self, actor: Principal, start: datetime | None, end: datetime | None) -> dict:
        self._require(actor, {"operations_manager", "administrator", "auditor", "department_manager"})
        window_start, window_end = default_window(self.clock.now())
        start = start or window_start
        end = end or window_end
        cases = []
        events_by_case = {}
        for case in self.store.list_requests():
            if not self._readable(actor, case):
                continue
            sla = self._sla(case)
            case = dict(case)
            case["met_resolution_target"] = sla["met_resolution_target"]
            cases.append(case)
            events_by_case[case["id"]] = self.store.list_where("case_events", "case_id", case["id"])
        visible_ids = {case["id"] for case in cases}
        return build_analytics(
            cases=cases,
            events_by_case=events_by_case,
            approvals=[row for row in self.store.list_all("approvals") if row["case_id"] in visible_ids],
            integrations=[row for row in self.store.list_all("integration_runs") if row.get("case_id") in visible_ids or row.get("case_id") is None],
            escalations=[row for row in self.store.list_all("escalations") if row["case_id"] in visible_ids],
            start=start,
            end=end,
            calendar=self.calendar,
        )

    def audit_events(self, actor: Principal) -> list[dict]:
        self._require(actor, {"auditor", "administrator", "operations_manager"})
        rows = []
        for event in self.store.list_all("audit_events"):
            if event.get("case_id"):
                case = self.store.get_request(event["case_id"])
                if case and not self._readable(actor, case):
                    continue
            rows.append(_public_event(event))
        return rows

    def timeline(self, actor: Principal, limit: int = 40) -> list[dict]:
        events = []
        for event in self.store.list_all("case_events"):
            case = self.store.get_request(event["case_id"])
            if not case or not self._readable(actor, case):
                continue
            public = _public_event(event)
            public["case_number"] = case["case_number"]
            public["title"] = case["title"]
            events.append(public)
        events.sort(key=lambda item: item["occurred_at"], reverse=True)
        return events[:limit]

    def _classify_and_route(
        self,
        conn,
        case: dict,
        correlation_id: str,
        at: datetime,
        *,
        manual_category: str | None = None,
        manual_reason: str | None = None,
        actor_id: str = SYSTEM.id,
    ) -> dict:
        case = self._hydrate(case)
        if manual_category:
            category = self.categories[manual_category]
            priority = higher_priority(case["priority"], category["priority_floor"])
            extracted = extract_structured_fields(case["description"])
            for key, value in extracted.items():
                case[key] = case.get(key) or value
            missing = missing_required_fields(category, case)
            fields = {
                "category_id": manual_category,
                "priority": priority,
                "manual_triage": 0 if not missing else 1,
                "classification_confidence": "manual",
                "classification_reason": manual_reason,
                "missing_information_json": json.dumps(missing),
                "resource_name": case.get("resource_name"),
                "justification": case.get("justification"),
                "preferred_window": case.get("preferred_window"),
                "due_at": add_business_minutes(
                    datetime.fromisoformat(case["submitted_at"]),
                    category["sla"][priority],
                    self.calendar,
                ).isoformat(),
            }
            reason = manual_reason or "A person chose the category."
            confidence = "manual"
            manual = bool(missing)
            security = bool(case["security_flag"])
        else:
            result = classify_text(case["title"], case["description"])
            extracted = extract_structured_fields(case["description"])
            for key, value in extracted.items():
                case[key] = case.get(key) or value
            category = self.categories.get(result.category_id or "")
            priority = result.priority
            if category:
                priority = higher_priority(priority, category["priority_floor"])
            missing = list(result.missing_information) + missing_required_fields(category, case)
            security = result.security_escalation
            manual = result.manual_triage or not result.category_id or bool(missing and result.confidence != "high")
            if missing:
                manual = True
            fields = {
                "category_id": result.category_id,
                "priority": priority,
                "manual_triage": 1 if manual else 0,
                "classification_confidence": result.confidence,
                "classification_reason": result.policy_reason,
                "missing_information_json": json.dumps(missing),
                "security_flag": 1 if security else 0,
                "resource_name": case.get("resource_name"),
                "justification": case.get("justification"),
                "preferred_window": case.get("preferred_window"),
            }
            if category:
                fields["due_at"] = add_business_minutes(
                    datetime.fromisoformat(case["submitted_at"]),
                    category["sla"][priority],
                    self.calendar,
                ).isoformat()
            reason = result.policy_reason
            confidence = result.confidence
        if case["approval_state"] in {"approved", "rejected", "pending"}:
            pass
        elif category and category["approval_policy"] == "required":
            fields["approval_state"] = case["approval_state"] if case["approval_state"] == "failed" else "not_required"
        else:
            fields["approval_state"] = "not_required"
        self._update(conn, case, fields)
        case = self._reload(case["id"])
        target = "awaiting_information" if missing else "classified"
        if case["status"] in {"new", "awaiting_information", "classified"} and case["status"] != target:
            if can_transition(case["status"], target):
                case = self._move(
                    conn,
                    case,
                    target,
                    actor_id,
                    reason,
                    correlation_id,
                    at,
                    action="request_classified",
                )
            else:
                self._journal(
                    conn,
                    case_id=case["id"],
                    actor_id=actor_id,
                    action="request_classified",
                    at=at,
                    source="local_policy_engine",
                    previous_state=case["status"],
                    new_state=case["status"],
                    reason=reason,
                    correlation_id=correlation_id,
                )
        else:
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=actor_id,
                action="request_classified",
                at=at,
                source="local_policy_engine",
                previous_state=case["status"],
                new_state=case["status"],
                reason=reason,
                correlation_id=correlation_id,
                metadata={"confidence": confidence},
            )
        self._run(
            conn,
            flow_id="OPS-02",
            operation="classify.case",
            correlation_id=correlation_id,
            case_id=case["id"],
            at=at,
            outcome="succeeded",
            message=reason,
        )
        decision = route_case(
            category_id=case.get("category_id"),
            requester_department=case["requester_department"],
            manual_triage=bool(case.get("manual_triage")),
            missing_information=bool(missing),
        )
        self._assignment(
            conn,
            case,
            team=decision.team,
            agent_id=None,
            rule_id=decision.rule_id,
            reason=decision.reason,
            outcome=decision.outcome,
            actor_id=SYSTEM.id,
            at=at + timedelta(milliseconds=10),
            rule_version=decision.rule_version,
        )
        route_fields = {
            "assigned_team": decision.team,
            "owning_department": decision.owning_department,
        }
        if decision.outcome != "assigned" or not decision.team:
            route_fields["blocking_reason"] = decision.reason
            self._update(conn, case, route_fields)
            self._notify(
                conn,
                channel="teams",
                template="routing_failed",
                summary=f"{case['case_number']} could not be assigned. {decision.reason}",
                case_id=case["id"],
                recipient="service-operations",
                at=at,
            )
            self._journal(
                conn,
                case_id=case["id"],
                actor_id=SYSTEM.id,
                action="routing_failed",
                at=at,
                source="local_policy_engine",
                reason=decision.reason,
                correlation_id=correlation_id,
            )
            self._run(
                conn,
                flow_id="OPS-03",
                operation="route.case",
                correlation_id=correlation_id,
                case_id=case["id"],
                at=at,
                outcome="failed",
                error_category="human_action",
                error_code="unassigned",
                message=decision.reason,
            )
        else:
            self._update(conn, case, route_fields)
            case = self._reload(case["id"])
            if case["status"] == "classified":
                case = self._move(
                    conn,
                    case,
                    "assigned",
                    SYSTEM.id,
                    decision.reason,
                    correlation_id,
                    at + timedelta(milliseconds=20),
                    action="case_routed",
                )
            else:
                self._journal(
                    conn,
                    case_id=case["id"],
                    actor_id=SYSTEM.id,
                    action="case_routed",
                    at=at,
                    source="local_policy_engine",
                    previous_state=case["status"],
                    new_state=case["status"],
                    reason=decision.reason,
                    correlation_id=correlation_id,
                    metadata={"rule_id": decision.rule_id, "rule_version": decision.rule_version},
                )
            self._run(
                conn,
                flow_id="OPS-03",
                operation="route.case",
                correlation_id=correlation_id,
                case_id=case["id"],
                at=at,
                outcome="succeeded",
                message=decision.reason,
            )
        if security:
            self._notify(
                conn,
                channel="teams",
                template="security_escalation",
                summary=f"{case['case_number']} contains urgent security language and needs a person.",
                case_id=case["id"],
                recipient="it-administrators",
                at=at,
            )
        return self._reload(case["id"])

    def _maybe_request_approval(self, conn, case: dict, correlation_id: str, at: datetime) -> dict:
        category = self.categories.get(case.get("category_id") or "")
        if not category or category["approval_policy"] != "required":
            return case
        if case.get("manual_triage") or case["status"] == "awaiting_information":
            return case
        if case["approval_state"] in {"pending", "approved", "rejected"}:
            return case
        if case["status"] not in {"assigned", "classified"}:
            return case
        return self._open_approval(conn, case, correlation_id, at)

    def _open_approval(self, conn, case: dict, correlation_id: str, at: datetime) -> dict:
        requester = self.store.get_requester(case["requester_id"])
        manager_id = requester.get("manager_id") if requester else None
        if manager_id and manager_id == case["requester_id"]:
            self._fail_approval(conn, case, correlation_id, at, "self_approval_blocked", "The requester is also recorded as the manager.")
            return self._reload(case["id"])
        if not manager_id or not self.store.get_requester(manager_id):
            self._fail_approval(
                conn,
                case,
                correlation_id,
                at,
                "missing_manager",
                "No manager is recorded for the requester. Nobody was invented as the approver.",
            )
            return self._reload(case["id"])
        if case["status"] == "assigned":
            case = self._move(
                conn,
                case,
                "awaiting_approval",
                SYSTEM.id,
                "Approval is required by category policy.",
                correlation_id,
                at,
                action="approval_requested",
                extra={"approval_state": "pending"},
            )
        else:
            self._update(conn, case, {"approval_state": "pending"})
        approval = {
            "id": new_id(),
            "case_id": case["id"],
            "approver_id": manager_id,
            "state": "pending",
            "requested_at": at.isoformat(),
            "decided_at": None,
            "comments": None,
            "decision_authority": "pending",
            "recorded_by": SYSTEM.id,
            "workflow_run_ref": None,
            "correlation_id": correlation_id,
            "requested_action": "Approve or reject the request. Approval does not grant access.",
        }
        self.store.insert_child(conn, "approvals", approval)
        self._notify(
            conn,
            channel="teams",
            template="approval_requested",
            summary=f"{case['case_number']} is waiting for a decision. The case title is held in OpsPilot.",
            case_id=case["id"],
            recipient=manager_id,
            at=at,
        )
        self._run(
            conn,
            flow_id="OPS-04",
            operation="approval.request",
            correlation_id=correlation_id,
            case_id=case["id"],
            at=at,
            outcome="succeeded",
            message="Approval row created. Microsoft Approvals was not started.",
        )
        return self._reload(case["id"])

    def _fail_approval(self, conn, case, correlation_id, at, code: str, reason: str) -> None:
        self._update(conn, case, {"approval_state": "failed", "blocking_reason": code})
        self._journal(
            conn,
            case_id=case["id"],
            actor_id=SYSTEM.id,
            action="approval_requested",
            at=at,
            source="local_policy_engine",
            previous_state=case["status"],
            new_state=case["status"],
            reason=reason,
            correlation_id=correlation_id,
            metadata={"error_code": code},
        )
        self._notify(
            conn,
            channel="teams",
            template="approval_failed",
            summary=f"{case['case_number']} has no usable approver.",
            case_id=case["id"],
            recipient="service-operations",
            at=at,
        )
        self._run(
            conn,
            flow_id="OPS-04",
            operation="approval.request",
            correlation_id=correlation_id,
            case_id=case["id"],
            at=at,
            outcome="failed",
            error_category="human_action",
            error_code=code,
            message=reason,
        )

    def _insert_case(self, conn, **kwargs) -> dict:
        number = kwargs["explicit_number"] or self.store.allocate_case_number(conn)
        case = {
            "id": new_id(),
            "case_number": number,
            "title": kwargs["title"],
            "description": kwargs["description"],
            "category_id": None,
            "requester_id": kwargs["requester_id"],
            "requester_department": kwargs["department"],
            "owning_department": None,
            "assigned_team": None,
            "assigned_agent_id": None,
            "priority": "normal",
            "status": "new",
            "approval_state": "not_required",
            "source_channel": kwargs["source_channel"],
            "source_message_id": kwargs["source_message_id"],
            "source_mailbox": kwargs["source_mailbox"],
            "dedup_key": kwargs["dedup_key"],
            "submitted_at": kwargs["submitted_at"].isoformat(),
            "due_at": None,
            "completed_at": None,
            "resolution_summary": None,
            "version": 1,
            "manual_triage": 0,
            "classification_confidence": None,
            "classification_reason": None,
            "missing_information_json": "[]",
            "correlation_id": kwargs["correlation_id"],
            "resource_name": kwargs["resource_name"],
            "justification": kwargs["justification"],
            "preferred_window": kwargs["preferred_window"],
            "security_flag": 0,
            "calendar_event_id": None,
            "blocking_reason": None,
        }
        self.store.insert_request(conn, case)
        return case

    def _move(
        self,
        conn,
        case: dict,
        target: str,
        actor_id: str,
        reason: str,
        correlation_id: str,
        at: datetime,
        *,
        action: str,
        extra: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        if not can_transition(case["status"], target):
            raise OpsError(
                "invalid_transition",
                f"A {case['status'].replace('_', ' ')} case cannot move to {target.replace('_', ' ')}.",
                409,
            )
        previous = case["status"]
        fields = {"status": target, **(extra or {})}
        self._update(conn, case, fields)
        self._journal(
            conn,
            case_id=case["id"],
            actor_id=actor_id,
            action=action,
            at=at,
            source="local_policy_engine",
            previous_state=previous,
            new_state=target,
            reason=reason,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        return self._reload(case["id"])

    def _update(self, conn, case: dict, fields: dict) -> None:
        current = self._reload(case["id"])
        if self.store.update_request(conn, case["id"], current["version"], fields) != 1:
            raise OpsError("conflict", "The case changed while it was being updated.", 409)

    def _acknowledge(self, conn, case: dict, at: datetime) -> None:
        body = (
            f"Case {case['case_number']} was received.\n"
            f"Title: {case['title']}\n"
            f"Received: {case['submitted_at']}\n"
            "Next step: the request will be classified and routed.\n"
            "Sign in to OpsPilot to view status. Do not include secrets in a reply."
        )
        self._communication(
            conn,
            case_id=case["id"],
            channel="outlook",
            direction="outbound",
            template="acknowledgement",
            body=body,
            status="not_delivered_channel_unconfigured",
            at=at,
            recipient=case["requester_id"],
        )

    def _communication(self, conn, **kwargs) -> None:
        self.store.insert_child(
            conn,
            "communications",
            {
                "id": new_id(),
                "case_id": kwargs["case_id"],
                "channel": kwargs["channel"],
                "direction": kwargs["direction"],
                "template": kwargs["template"],
                "safe_body": kwargs["body"],
                "delivery_status": kwargs["status"],
                "created_at": kwargs["at"].isoformat(),
                "recipient_ref": kwargs["recipient"],
            },
        )

    def _assignment(self, conn, case, **kwargs) -> None:
        self.store.insert_child(
            conn,
            "assignments",
            {
                "id": new_id(),
                "case_id": case["id"],
                "team": kwargs["team"],
                "agent_id": kwargs["agent_id"],
                "rule_id": kwargs["rule_id"],
                "rule_version": kwargs.get("rule_version") or "2026.11.0",
                "reason": kwargs["reason"],
                "created_at": kwargs["at"].isoformat(),
                "actor_id": kwargs["actor_id"],
                "outcome": kwargs["outcome"],
            },
        )

    def _notify(self, conn, **kwargs) -> None:
        status = "not_delivered_channel_unconfigured"
        if kwargs["channel"] == "teams" and self.settings.teams_configured:
            try:
                response = httpx.post(
                    self.settings.teams_webhook_url,
                    json={"text": kwargs["summary"]},
                    timeout=10,
                )
                status = "delivered" if response.status_code < 400 else "failed"
            except httpx.HTTPError:
                status = "failed"
        self.store.insert_child(
            conn,
            "notifications",
            {
                "id": new_id(),
                "case_id": kwargs["case_id"],
                "channel": kwargs["channel"],
                "template": kwargs["template"],
                "status": status,
                "created_at": kwargs["at"].isoformat(),
                "safe_summary": kwargs["summary"],
                "recipient_ref": kwargs["recipient"],
            },
        )

    def _escalation(self, conn, case, key: str, threshold: str, at: datetime, correlation_id: str) -> bool:
        exists = conn.execute("SELECT 1 FROM escalations WHERE dedup_key = ?", (key,)).fetchone()
        if exists:
            return False
        reason = f"Resolution SLA is {threshold.replace('_', ' ')}."
        self.store.insert_child(
            conn,
            "escalations",
            {
                "id": new_id(),
                "case_id": case["id"],
                "dedup_key": key,
                "reason": reason,
                "created_at": at.isoformat(),
                "notified_status": "not_delivered_channel_unconfigured",
                "threshold": threshold,
            },
        )
        action = "escalation" if threshold == "breached" else "sla_warning"
        self._journal(
            conn,
            case_id=case["id"],
            actor_id=SYSTEM.id,
            action=action,
            at=at,
            source="local_policy_engine",
            reason=reason,
            correlation_id=correlation_id,
            metadata={"flow_id": "OPS-06", "cloud_flow_executed": False},
        )
        self._notify(
            conn,
            channel="teams",
            template=action,
            summary=f"{case['case_number']} {reason}",
            case_id=case["id"],
            recipient="service-operations",
            at=at,
        )
        return True

    def _run(self, conn, **kwargs) -> str:
        run_id = new_id()
        self.store.insert_child(
            conn,
            "integration_runs",
            {
                "id": run_id,
                "flow_name": LOCAL_FLOW_NAMES[kwargs["flow_id"]],
                "flow_id": kwargs["flow_id"],
                "source": kwargs.get("source") or "local_policy_engine",
                "operation": kwargs["operation"],
                "run_ref": None,
                "correlation_id": kwargs["correlation_id"],
                "case_id": kwargs["case_id"],
                "trigger_name": kwargs["operation"],
                "started_at": kwargs["at"].isoformat(),
                "completed_at": kwargs["at"].isoformat(),
                "outcome": kwargs["outcome"],
                "error_category": kwargs.get("error_category"),
                "error_code": kwargs.get("error_code"),
                "safe_message": kwargs.get("message"),
                "attempt": kwargs.get("attempt") or 1,
                "predecessor_id": kwargs.get("predecessor_id"),
            },
        )
        return run_id

    def _journal(self, conn, **kwargs) -> None:
        self._event(conn, case_event=True, **kwargs)

    def _audit(self, conn, **kwargs) -> None:
        self._event(conn, case_event=False, **kwargs)

    def _event(self, conn, *, case_event: bool, **kwargs) -> None:
        row = {
            "id": new_id(),
            "case_id": kwargs.get("case_id"),
            "actor_id": kwargs.get("actor_id"),
            "action": kwargs["action"],
            "occurred_at": kwargs["at"].isoformat(),
            "source_system": kwargs["source"],
            "previous_state": kwargs.get("previous_state"),
            "new_state": kwargs.get("new_state"),
            "reason": kwargs.get("reason"),
            "correlation_id": kwargs.get("correlation_id"),
            "integration_ref": kwargs.get("integration_ref"),
            "safe_metadata_json": json.dumps(kwargs.get("metadata") or {}),
        }
        if case_event and row["case_id"]:
            self.store.insert_child(conn, "case_events", row)
            audit = dict(row)
            audit["id"] = new_id()
            self.store.insert_child(conn, "audit_events", audit)
        else:
            self.store.insert_child(conn, "audit_events", row)

    def _sla(self, case: dict, events: list[dict] | None = None) -> dict:
        category = self.categories.get(case.get("category_id") or "")
        target = category["sla"][case["priority"]] if category else None
        if events is None:
            events = self.store.list_where("case_events", "case_id", case["id"])
        completed = None
        if case.get("completed_at"):
            completed = datetime.fromisoformat(case["completed_at"])
        return evaluate_sla(
            status=case["status"],
            submitted_at=datetime.fromisoformat(case["submitted_at"]),
            now=self.clock.now(),
            target_minutes=target,
            events=events,
            calendar=self.calendar,
            completed_at=completed,
        )

    def _tool_envelope(self, case: dict, actor: Principal) -> dict:
        hydrated = self._hydrate(case)
        category = self.categories.get(hydrated.get("category_id") or "")
        events = self.store.list_where("case_events", "case_id", case["id"])
        updated = events[-1]["occurred_at"] if events else case["submitted_at"]
        return {
            "success": True,
            "case_id": case["id"],
            "case_number": case["case_number"],
            "status": case["status"],
            "approval_state": case["approval_state"],
            "message": status_sentence(hydrated, category["name"] if category else None),
            "next_action": next_action(hydrated),
            "updated_at": updated,
            "error_code": None,
            "candidates": [],
        }

    def _empty_tool(self, message: str, code: str) -> dict:
        return {
            "success": True,
            "case_id": None,
            "case_number": None,
            "status": None,
            "message": message,
            "next_action": None,
            "updated_at": self.clock.now().isoformat(),
            "error_code": code,
            "candidates": [],
        }

    def _case_for(self, actor: Principal, case_id: str) -> dict:
        case = self.store.get_request(case_id)
        if not case or not self._readable(actor, case):
            if case and not self._readable(actor, case):
                with self.store.session() as conn:
                    self._audit(
                        conn,
                        case_id=case["id"],
                        actor_id=actor.id,
                        action="access_denied",
                        at=self.clock.now(),
                        source="api",
                        reason="The caller is not allowed to view this case.",
                        correlation_id=str(uuid.uuid4()),
                        metadata={"case_number": case["case_number"]},
                    )
            raise OpsError("not_found", "Case not found.", 404)
        return case

    def _readable(self, actor: Principal, case: dict) -> bool:
        approvals = self.store.list_where("approvals", "case_id", case["id"])
        return can_read(actor, case, approvals)

    def _must(self, case_id: str) -> dict:
        case = self.store.get_request(case_id)
        if not case:
            raise OpsError("not_found", "Case not found.", 404)
        return case

    def _reload(self, case_id: str) -> dict:
        case = self.store.get_request(case_id)
        if not case:
            raise OpsError("not_found", "Case not found.", 404)
        return case

    def _latest_runs(self) -> dict[tuple, dict]:
        latest: dict[tuple, dict] = {}
        for run in self.store.list_all("integration_runs"):
            latest[(run.get("case_id"), run["operation"])] = run
        return latest

    def _hydrate(self, case: dict) -> dict:
        data = dict(case)
        raw = data.pop("missing_information_json", "[]")
        data["missing_information"] = json.loads(raw or "[]")
        data["manual_triage"] = bool(data.get("manual_triage"))
        data["security_flag"] = bool(data.get("security_flag"))
        return data

    @staticmethod
    def _principal(person: dict) -> Principal:
        return Principal(
            id=person["id"],
            display_name=person["display_name"],
            role=person["role"],
            department=person["department"],
            teams=tuple(person.get("teams") or []),
            upn=person["upn"],
        )

    @staticmethod
    def _require(actor: Principal, roles: set[str]) -> None:
        if actor.role not in roles:
            raise OpsError("forbidden", "You cannot perform that action.", 403)


def _auto_reply(subject: str, headers: dict) -> bool:
    lowered = {str(key).lower(): str(value).lower() for key, value in headers.items()}
    auto = lowered.get("auto-submitted", "no")
    if auto not in {"no", ""}:
        return True
    title = subject.lower()
    return title.startswith("automatic reply") or title.startswith("out of office")


def _graph_time(moment: datetime) -> dict:
    utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return {"dateTime": utc.isoformat(timespec="seconds"), "timeZone": "UTC"}


def _fulfilment_destination(category_id: str, case: dict) -> tuple[str, str | None]:
    if category_id == "access_request":
        return "IT Service Desk", "IT"
    if category_id == "scheduling_request":
        return "Operations Scheduling", "Operations"
    return case.get("assigned_team") or "Service Operations", case.get("owning_department")


def _attention(kind: str, case: dict, detail: str) -> dict:
    return {
        "kind": kind,
        "case_id": case["id"],
        "case_number": case["case_number"],
        "title": case["title"],
        "detail": detail,
        "status": case["status"],
        "priority": case["priority"],
    }


def _public_event(event: dict) -> dict:
    metadata = event.get("safe_metadata_json") or "{}"
    if isinstance(metadata, str):
        metadata = json.loads(metadata or "{}")
    return {
        "id": event["id"],
        "case_id": event.get("case_id"),
        "actor_id": event.get("actor_id"),
        "action": event["action"],
        "occurred_at": event["occurred_at"],
        "source_system": event["source_system"],
        "previous_state": event.get("previous_state"),
        "new_state": event.get("new_state"),
        "reason": event.get("reason"),
        "correlation_id": event.get("correlation_id"),
        "integration_ref": event.get("integration_ref"),
        "metadata": metadata,
    }


def _name_people(approvals: list[dict], store: Store) -> list[dict]:
    named = []
    for row in approvals:
        approver = store.get_requester(row["approver_id"]) if row.get("approver_id") else None
        named.append({**row, "approver_name": approver["display_name"] if approver else None})
    return named


def body_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
