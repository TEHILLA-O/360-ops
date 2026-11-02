"""HTTP routes. Authorisation is decided in the engine, not in the browser."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.api.deps import actor_from, capability_report, parse_time, session_token
from app.domain.categories import CATEGORIES
from app.domain.transitions import ALLOWED
from app.errors import OpsError
from app.services.engine import body_hash
from app.services.pdf_export import render_pdf

router = APIRouter(prefix="/api")


class WebCase(BaseModel):
    title: str
    description: str
    resource_name: str | None = None
    justification: str | None = None
    preferred_window: str | None = None


class InboundMail(BaseModel):
    mailbox: str
    message_id: str
    subject: str
    body: str = ""
    sender_upn: str
    headers: dict[str, str] = Field(default_factory=dict)
    process: bool = True


class ManualClass(BaseModel):
    category_id: str
    reason: str


class TextBody(BaseModel):
    text: str


class Question(BaseModel):
    question: str


class Decision(BaseModel):
    decision: str
    comments: str


class SummaryBody(BaseModel):
    summary: str


class ReasonBody(BaseModel):
    reason: str


class DocumentBody(BaseModel):
    filename: str
    doc_type: str = "reference"


class ScheduleBody(BaseModel):
    start: datetime
    end: datetime


class Enquiry(BaseModel):
    text: str


class Escalate(BaseModel):
    question: str
    case_id: str | None = None


def _remember(request: Request, key: str | None, digest: str, status: int, payload: dict) -> None:
    if not key:
        return
    with request.app.state.store.session() as conn:
        request.app.state.store.insert_idempotency(conn, key, digest, status, payload)


def _idempotent(request: Request, digest: str):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return None, None
    existing = request.app.state.store.get_idempotency(key)
    if existing and existing["request_hash"] != digest:
        raise OpsError("idempotency_conflict", "This idempotency key was already used for a different request.", 409)
    if existing:
        return key, JSONResponse(status_code=existing["status_code"], content=json.loads(existing["response_json"]))
    return key, None


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "service": "opspilot365",
        "auth_mode": request.app.state.settings.auth_mode,
        "data_plane": "local_sqlite_case_store",
        "cloud_flows_deployed": False,
    }


@router.get("/capabilities")
def capabilities(request: Request):
    return capability_report(request.app.state.settings)


@router.get("/personas")
def personas(request: Request):
    return {
        "identity_source": "local_synthetic_directory" if request.app.state.settings.auth_mode == "local_synthetic" else "entra",
        "personas": request.app.state.engine.list_personas(),
    }


@router.get("/categories")
def categories():
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "required_fields": item["required_fields"],
            "approval_policy": item["approval_policy"],
            "priority_floor": item["priority_floor"],
            "fulfilment_required": item["fulfilment_required"],
            "sla_resolution_business_minutes": item["sla"],
            "first_response_business_minutes": item["first_response_minutes"],
            "resolution_requirements": item["resolution_requirements"],
        }
        for item in CATEGORIES
    ]


@router.get("/transitions")
def transitions():
    return {status: sorted(targets) for status, targets in ALLOWED.items()}


@router.get("/cases")
def list_cases(request: Request):
    actor = actor_from(request)
    return request.app.state.engine.list_visible(actor)


@router.get("/cases/{case_id}")
def get_case(case_id: str, request: Request):
    actor = actor_from(request)
    case = request.app.state.store.get_request(case_id)
    if not case:
        by_number = request.app.state.store.get_request_by_number(case_id)
        case = by_number
    if not case:
        raise OpsError("not_found", "Case not found.", 404)
    return request.app.state.engine.present(case, actor, detail=True)


@router.post("/cases")
def create_case(body: WebCase, request: Request):
    actor = actor_from(request)
    digest = body_hash(body.model_dump())
    key, replay = _idempotent(request, digest)
    if replay:
        return replay
    payload = request.app.state.engine.submit_web(
        actor,
        title=body.title,
        description=body.description,
        resource_name=body.resource_name,
        justification=body.justification,
        preferred_window=body.preferred_window,
        correlation_id=request.state.correlation_id,
    )
    _remember(request, key, digest, 200, payload)
    return payload


@router.post("/intake/outlook")
def intake(body: InboundMail, request: Request):
    actor = actor_from(request)
    digest = body_hash(body.model_dump())
    key, replay = _idempotent(request, digest)
    if replay:
        return replay
    payload = request.app.state.engine.ingest_message(
        actor,
        body.model_dump(),
        process=body.process,
        correlation_id=request.state.correlation_id,
    )
    _remember(request, key, digest, 200, payload)
    return payload


@router.post("/cases/{case_id}/classify")
def classify(case_id: str, body: ManualClass, request: Request):
    return request.app.state.engine.classify_manual(
        actor_from(request), case_id, body.category_id, body.reason, request.state.correlation_id
    )


@router.post("/cases/{case_id}/clarification")
def clarify(case_id: str, body: TextBody, request: Request):
    return request.app.state.engine.submit_clarification(
        actor_from(request), case_id, body.text, request.state.correlation_id
    )


@router.post("/cases/{case_id}/request-clarification")
def ask(case_id: str, body: Question, request: Request):
    return request.app.state.engine.request_clarification(
        actor_from(request), case_id, body.question, request.state.correlation_id
    )


@router.post("/cases/{case_id}/accept")
def accept(case_id: str, request: Request):
    return request.app.state.engine.accept_work(actor_from(request), case_id, request.state.correlation_id)


@router.post("/approvals/{approval_id}/simulate-decision")
def simulate(approval_id: str, body: Decision, request: Request):
    return request.app.state.engine.record_simulated_decision(
        actor_from(request), approval_id, body.decision, body.comments, request.state.correlation_id
    )


@router.post("/cases/{case_id}/fulfilment")
def fulfil(case_id: str, body: SummaryBody, request: Request):
    return request.app.state.engine.record_fulfilment(
        actor_from(request), case_id, body.summary, request.state.correlation_id
    )


@router.post("/cases/{case_id}/resolve")
def resolve(case_id: str, body: SummaryBody, request: Request):
    return request.app.state.engine.resolve_case(
        actor_from(request), case_id, body.summary, request.state.correlation_id
    )


@router.post("/cases/{case_id}/close")
def close_case(case_id: str, body: ReasonBody, request: Request):
    return request.app.state.engine.close_case(actor_from(request), case_id, body.reason, request.state.correlation_id)


@router.post("/cases/{case_id}/cancel")
def cancel(case_id: str, body: ReasonBody, request: Request):
    return request.app.state.engine.cancel_case(actor_from(request), case_id, body.reason, request.state.correlation_id)


@router.post("/cases/{case_id}/reopen")
def reopen(case_id: str, body: ReasonBody, request: Request):
    return request.app.state.engine.reopen_case(actor_from(request), case_id, body.reason, request.state.correlation_id)


@router.post("/cases/{case_id}/documents")
def add_document(case_id: str, body: DocumentBody, request: Request):
    return request.app.state.engine.add_document_reference(
        actor_from(request),
        case_id,
        filename=body.filename,
        doc_type=body.doc_type,
        source="manual_reference",
        correlation_id=request.state.correlation_id,
    )


@router.post("/cases/{case_id}/schedule")
def schedule(case_id: str, body: ScheduleBody, request: Request):
    if body.end <= body.start:
        raise OpsError("invalid_request", "The appointment end must be after the start.", 422)
    return request.app.state.engine.schedule_appointment(
        actor_from(request),
        case_id,
        token=session_token(request),
        start=body.start,
        end=body.end,
        correlation_id=request.state.correlation_id,
    )


@router.get("/approvals")
def approvals(request: Request):
    actor = actor_from(request)
    rows = []
    for case in request.app.state.engine.list_visible(actor):
        detail = request.app.state.engine.present(request.app.state.store.get_request(case["id"]), actor, detail=True)
        for approval in detail["approvals"]:
            rows.append({**approval, "case_number": case["case_number"], "title": case["title"], "case_status": case["status"]})
    return rows


@router.get("/command")
def command(request: Request):
    return request.app.state.engine.command(actor_from(request))


@router.get("/attention")
def attention(request: Request):
    return request.app.state.engine.attention(actor_from(request))


@router.get("/timeline")
def timeline(request: Request, limit: int = 40):
    return request.app.state.engine.timeline(actor_from(request), min(limit, 100))


@router.get("/workflows")
def workflows(request: Request):
    actor_from(request)
    return request.app.state.engine.workflow_board()


@router.get("/integrations")
def integrations(request: Request):
    actor = actor_from(request)
    if actor.role not in {"administrator", "operations_manager", "auditor"}:
        raise OpsError("forbidden", "You cannot inspect integration runs.", 403)
    return request.app.state.store.list_all("integration_runs")


@router.post("/integrations/{run_id}/retry")
def retry(run_id: str, request: Request):
    return request.app.state.engine.retry_integration(
        actor_from(request), run_id, session_token(request), request.state.correlation_id
    )


@router.post("/sla/sweep")
def sweep(request: Request):
    return request.app.state.engine.sweep_sla(actor_from(request))


@router.get("/analytics")
def analytics(request: Request, start: str | None = None, end: str | None = None):
    return request.app.state.engine.analytics(actor_from(request), parse_time(start), parse_time(end))


@router.get("/audit")
def audit(request: Request):
    return request.app.state.engine.audit_events(actor_from(request))


@router.get("/audit/export")
def export_audit(request: Request, export_format: str = "csv"):
    actor = actor_from(request)
    rows = request.app.state.engine.audit_events(actor)
    generated = request.app.state.clock.now().isoformat()
    with request.app.state.store.session() as conn:
        request.app.state.engine._audit(
            conn,
            case_id=None,
            actor_id=actor.id,
            action="audit_exported",
            at=request.app.state.clock.now(),
            source="api",
            reason=f"Exported {len(rows)} audit rows as {export_format}.",
            correlation_id=request.state.correlation_id,
            metadata={"format": export_format, "row_count": len(rows)},
        )
    if export_format == "json":
        return {
            "generated_at": generated,
            "filters": "actor visibility",
            "evidence_source": "audit_events",
            "events": rows,
        }
    if export_format == "pdf":
        lines = [
            "OpsPilot 365 audit export",
            f"Generated: {generated}",
            "Source: audit_events",
            "Filter: records visible to the signed-in role",
            "",
        ]
        for event in rows:
            lines.append(
                f"{event['occurred_at']}  {event['action']}  case={event.get('case_id') or '-'}  actor={event.get('actor_id') or '-'}"
            )
        return Response(content=render_pdf(lines), media_type="application/pdf")
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["occurred_at", "action", "case_id", "actor_id", "source_system", "previous_state", "new_state", "reason", "correlation_id"],
    )
    writer.writeheader()
    for event in rows:
        writer.writerow({key: event.get(key) for key in writer.fieldnames})
    return Response(
        content=f"# generated_at={generated}\n# evidence_source=audit_events\n" + buffer.getvalue(),
        media_type="text/csv",
    )


@router.get("/documents")
def documents(request: Request):
    actor = actor_from(request)
    rows = []
    for case in request.app.state.engine.list_visible(actor):
        for document in request.app.state.store.list_where("document_references", "case_id", case["id"]):
            rows.append({**document, "case_number": case["case_number"], "sharepoint_connected": False})
    return rows


@router.get("/connections")
def connections(request: Request):
    actor_from(request)
    health = request.app.state.engine.service_health()
    return [
        {"id": "outlook", "name": "Outlook", "state": health["outlook_connector"], "detail": "Intake is specified as OPS-01 and is not deployed."},
        {"id": "teams", "name": "Teams", "state": health["teams"], "detail": "Notifications are recorded locally until a webhook or connector exists."},
        {"id": "graph", "name": "Microsoft Graph", "state": health["graph"], "detail": "Delegated /me calls only. No application permission is requested."},
        {"id": "sharepoint", "name": "SharePoint", "state": health["sharepoint"], "detail": "Case documents are metadata references, not downloaded files."},
        {"id": "dataverse", "name": "Dataverse", "state": health["dataverse"], "detail": "The running store is SQLite. The Dataverse schema is a specification."},
        {"id": "copilot", "name": "Copilot Studio", "state": health["copilot_studio"], "detail": "Agent topics and tool contracts are authoring assets, not a published bot."},
        {"id": "power_automate", "name": "Power Automate", "state": health["power_automate"], "detail": "No cloud flow run has been ingested."},
    ]


@router.post("/connections/{name}/probe")
def probe(name: str, request: Request):
    actor = actor_from(request)
    if actor.role not in {"administrator", "operations_manager"}:
        raise OpsError("forbidden", "You cannot run connection probes.", 403)
    if name == "case-store":
        return {"ok": True, "state": "available", "cases": request.app.state.store.count_requests()}
    if name == "graph":
        call = request.app.state.graph.get_me(session_token(request))
        return {
            "ok": call.ok,
            "state": "connected" if call.ok else call.error_code,
            "message": call.message,
            "profile": call.body if call.ok else None,
        }
    if name in {"outlook", "teams", "sharepoint", "dataverse", "copilot", "power-automate"}:
        return {"ok": False, "state": "not_configured", "message": "This Microsoft service is not connected in the current environment."}
    raise OpsError("not_found", "Unknown connection.", 404)


@router.get("/graph/me")
def graph_me(request: Request):
    return _graph_http(request.app.state.graph.get_me(session_token(request)))


@router.get("/graph/messages")
def graph_messages(request: Request):
    return _graph_http(request.app.state.graph.list_messages(session_token(request)))


@router.get("/graph/drive/children")
def graph_drive(request: Request):
    return _graph_http(request.app.state.graph.list_drive_children(session_token(request)))


@router.post("/graph/events")
def graph_event(body: ScheduleBody, request: Request):
    """Connection probe on the signed-in user's own calendar. It does not update a case."""
    if body.end <= body.start or body.end - body.start > timedelta(hours=2):
        raise OpsError("invalid_request", "Probe events must be two hours or shorter.", 422)
    payload = {
        "subject": "OpsPilot 365 connection probe",
        "body": {"contentType": "Text", "content": "Created by an authorised OpsPilot connection probe."},
        "start": {"dateTime": _utc_stamp(body.start), "timeZone": "UTC"},
        "end": {"dateTime": _utc_stamp(body.end), "timeZone": "UTC"},
    }
    # The engine's Graph client is the only caller. A missing token returns not_authenticated
    # and does not invent an event id.
    return _graph_http(request.app.state.graph.create_event(session_token(request), payload))


@router.post("/assistant/create-request")
def assistant_create(body: WebCase, request: Request):
    return create_case(body, request)


@router.post("/assistant/status")
def assistant_status(body: Enquiry, request: Request):
    return request.app.state.engine.enquire(actor_from(request), body.text)


@router.post("/assistant/my-requests")
def assistant_mine(request: Request):
    return request.app.state.engine.my_open_requests(actor_from(request))


@router.post("/assistant/explain-approval")
def assistant_approval(request: Request, case_id: str | None = None):
    return request.app.state.engine.explain_approval(actor_from(request), case_id)


@router.post("/assistant/guidance")
def assistant_guidance(request: Request, category_id: str | None = None):
    return request.app.state.engine.guidance(category_id)


@router.post("/assistant/escalate")
def assistant_escalate(body: Escalate, request: Request):
    return request.app.state.engine.escalate_question(actor_from(request), body.question, body.case_id)


@router.post("/assistant/clarification")
def assistant_clarification(case_id: str, body: TextBody, request: Request):
    return clarify(case_id, body, request)


def _utc_stamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _graph_http(call):
    payload = _graph_response(call)
    if call.ok:
        return payload
    return JSONResponse(status_code=call.status or 503, content=payload)


def _graph_response(call) -> dict:
    return {
        "ok": call.ok,
        "status": call.status,
        "error_code": call.error_code,
        "error_category": call.error_category,
        "message": call.message,
        "attempts": call.attempts,
        "operation": call.operation,
        "body": call.body if call.ok else None,
    }
