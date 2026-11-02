import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def api(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, seed=True, auth_mode="local_synthetic"))
    with TestClient(app) as client:
        yield client


def _as(client: TestClient, persona: str):
    client.headers["X-OpsPilot-Actor"] = persona
    return client


def _case(client: TestClient, number: str) -> dict:
    rows = client.get("/api/cases").json()
    match = next(row for row in rows if row["case_number"] == number)
    return client.get(f"/api/cases/{match['id']}").json()


def test_finance_access_is_approved_and_waiting_for_a_person(api):
    _as(api, "maya.chen")
    case = _case(api, "NS-2401")
    assert case["status"] == "awaiting_fulfilment"
    assert case["approval_state"] == "approved"
    assert case["assigned_team"] == "IT Service Desk"
    assert case["status_sentence"] == (
        "Your finance folder access request is approved and is awaiting fulfilment by the IT Service Desk."
    )
    assert "does not grant" in case["next_action"].lower() or "OpsPilot does not grant" in case["next_action"]
    assert case["approvals"][0]["decision_authority"] == "local_simulation"
    assert case["approvals"][0]["comments"] is None
    assert any(event["action"] == "request_received" for event in case["events"])
    assert case["calendar_event_id"] is None


def test_employee_cannot_read_someone_elses_case_by_number(api):
    _as(api, "samir.rahman")
    sofia = _case(api, "NS-2394")
    _as(api, "maya.chen")
    denied = api.get(f"/api/cases/{sofia['id']}")
    assert denied.status_code == 404
    assert sofia["title"] not in denied.text
    _as(api, "edith.lang")
    audit = api.get("/api/audit").json()
    assert any(event["action"] == "access_denied" and event["case_id"] == sofia["id"] for event in audit)


def test_rejection_does_not_open_fulfilment(api):
    _as(api, "sofia.almeida")
    case = _case(api, "NS-2394")
    assert case["status"] == "rejected"
    assert case["approval_state"] == "rejected"
    assert all(row["team"] != "IT Service Desk" for row in case["assignments"])
    assert "rejected" in case["status_sentence"].lower()
    _as(api, "samir.rahman")
    blocked = api.post(f"/api/cases/{case['id']}/fulfilment", json={"summary": "Trying to fulfil a rejection."})
    assert blocked.status_code == 409
    assert blocked.json()["error_code"] == "fulfilment_blocked"


def test_duplicate_outlook_message_does_not_create_a_second_case(api):
    _as(api, "grace.elliott")
    first = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "servicedesk@northstar.example",
            "message_id": "msg-fresh-1",
            "subject": "Printer jam on the second floor",
            "body": "The operations printer jams on every long document.",
            "sender_upn": "noah.briggs@northstar.example",
        },
    )
    assert first.status_code == 200
    second = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "servicedesk@northstar.example",
            "message_id": "msg-fresh-1",
            "subject": "Printer jam on the second floor",
            "body": "The operations printer jams on every long document.",
            "sender_upn": "noah.briggs@northstar.example",
        },
    )
    assert second.json()["outcome"] == "duplicate"
    assert second.json()["case_id"] == first.json()["case_id"]
    numbers = [row["case_number"] for row in api.get("/api/cases").json()]
    assert numbers.count(first.json()["case_number"]) == 1


def test_auto_reply_and_wrong_mailbox_and_unknown_sender_create_nothing(api):
    _as(api, "grace.elliott")
    before = api.get("/api/cases").json()
    auto = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "servicedesk@northstar.example",
            "message_id": "msg-auto",
            "subject": "Automatic reply: out of office",
            "body": "I am away.",
            "sender_upn": "maya.chen@northstar.example",
            "headers": {"Auto-Submitted": "auto-replied"},
        },
    )
    assert auto.json()["reason"] == "auto_reply"
    wrong = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "personal@northstar.example",
            "message_id": "msg-wrong",
            "subject": "Laptop replacement",
            "body": "My laptop will not start.",
            "sender_upn": "maya.chen@northstar.example",
        },
    )
    assert wrong.status_code == 422
    unknown = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "servicedesk@northstar.example",
            "message_id": "msg-unknown",
            "subject": "Laptop replacement",
            "body": "My laptop will not start and I need a technician.",
            "sender_upn": "stranger@northstar.example",
        },
    )
    assert unknown.status_code == 422
    assert unknown.json()["error_code"] == "unknown_requester"
    assert len(api.get("/api/cases").json()) == len(before)


def test_reply_cannot_attach_to_another_persons_case(api):
    _as(api, "grace.elliott")
    crossed = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "servicedesk@northstar.example",
            "message_id": "msg-cross",
            "subject": "Re: NS-2401 please send the payroll file",
            "body": "Here is a confidential payroll note that must not land on Maya's case.",
            "sender_upn": "jonah.adeyemi@northstar.example",
        },
    )
    assert crossed.status_code == 404
    _as(api, "maya.chen")
    case = _case(api, "NS-2401")
    assert "payroll" not in json.dumps(case).lower()


def test_status_enquiry_matches_the_stored_case_and_hides_other_people(api):
    _as(api, "maya.chen")
    response = api.post("/api/assistant/status", json={"text": "What's happening with my finance access request?"})
    body = response.json()
    assert body["case_number"] == "NS-2401"
    assert body["status"] == "awaiting_fulfilment"
    assert body["approval_state"] == "approved"
    assert "approved" in body["message"]
    assert "awaiting fulfilment" in body["message"]
    leaked = api.post("/api/assistant/status", json={"text": "What's happening with NS-2394?"})
    assert leaked.json()["case_id"] is None
    assert leaked.json()["error_code"] == "no_match"


def test_missing_information_stays_paused_until_detail_arrives(api):
    _as(api, "omar.farouk")
    case = _case(api, "NS-2388")
    assert case["status"] == "awaiting_information"
    assert case["sla_state"] == "paused"
    updated = api.post(
        f"/api/cases/{case['id']}/clarification",
        json={"text": "The loading dock shutter is stuck open.\nIt is a facilities maintenance problem."},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] != "awaiting_information"


def test_missing_manager_does_not_invent_an_approver(api):
    _as(api, "chris.holm")
    case = _case(api, "NS-2404")
    assert case["approval_state"] == "failed"
    assert case["blocking_reason"] == "missing_manager"
    assert all(row["approver_id"] is None or row["state"] != "pending" for row in case["approvals"])
    assert case["approvals"] == [] or all(row["approver_name"] is None for row in case["approvals"])


def test_graph_failure_does_not_complete_the_scheduling_case(api):
    _as(api, "pauline.vogel")
    case = _case(api, "NS-2419")
    assert case["status"] != "resolved"
    assert case["calendar_event_id"] is None
    assert any(run["outcome"] == "failed" and run["operation"] == "graph.create_event" for run in case["integrations"])
    _as(api, "nora.berg")
    probe = api.get("/api/graph/me")
    assert probe.status_code == 401
    assert probe.json()["ok"] is False
    assert probe.json()["body"] is None


def test_sla_breach_is_recorded_once(api):
    _as(api, "lucia.romero")
    case = _case(api, "NS-2310")
    assert case["sla_state"] == "breached"
    assert len(case["escalations"]) == 1
    _as(api, "nora.berg")
    again = api.post("/api/sla/sweep")
    assert again.status_code == 200
    assert "NS-2310" not in again.json()["created_case_numbers"]
    _as(api, "lucia.romero")
    assert len(_case(api, "NS-2310")["escalations"]) == 1


def test_closed_case_cannot_be_marked_approved(api):
    _as(api, "ingrid.solberg")
    case = _case(api, "NS-2290")
    assert case["status"] == "closed"
    _as(api, "samir.rahman")
    denied = api.post(f"/api/cases/{case['id']}/accept")
    assert denied.status_code == 409


def test_employee_cannot_forge_intake_and_system_persona_is_rejected(api):
    _as(api, "maya.chen")
    forged = api.post(
        "/api/intake/outlook",
        json={
            "mailbox": "servicedesk@northstar.example",
            "message_id": "msg-forged",
            "subject": "Laptop replacement",
            "body": "My laptop will not start.",
            "sender_upn": "jonah.adeyemi@northstar.example",
        },
    )
    assert forged.status_code == 403
    api.headers["X-OpsPilot-Actor"] = "policy.engine"
    assert api.get("/api/cases").status_code == 401


def test_idempotency_key_replays_the_same_body_and_rejects_a_different_one(api):
    _as(api, "ben.carter")
    payload = {
        "title": "Second monitor request",
        "description": "The docking station only drives one display and I cannot run the dashboard.",
    }
    headers = {"Idempotency-Key": "bench-1"}
    first = api.post("/api/cases", json=payload, headers=headers)
    second = api.post("/api/cases", json=payload, headers=headers)
    assert first.json()["case_id"] == second.json()["case_id"]
    clash = api.post(
        "/api/cases",
        json={"title": "Different", "description": "This is a different request with enough detail."},
        headers=headers,
    )
    assert clash.status_code == 409


def test_analytics_bottleneck_is_computed_and_cloud_runs_are_zero(api):
    _as(api, "edith.lang")
    report = api.get("/api/analytics").json()
    assert report["power_automate_runs_in_window"] == 0
    assert report["metrics"]["received"] > 0
    if report["bottleneck"]:
        assert report["bottleneck"]["statement"].endswith("of recorded waiting time in the selected period.")
        assert 0 < report["bottleneck"]["share_of_approval_wait"] <= 1
    board = api.get("/api/workflows").json()
    assert all(flow["deployed"] is False for flow in board["flows"])
    assert all(flow["observed_cloud_runs"] == 0 for flow in board["flows"])
    assert "not a" in board["note"] or "not Power Automate" in board["note"] or "callbacks" in board["note"]


def test_graph_retry_does_not_mark_success_when_still_unauthenticated(api):
    _as(api, "nora.berg")
    runs = api.get("/api/integrations").json()
    failed = next(run for run in runs if run["operation"] == "graph.create_event" and run["outcome"] == "failed")
    retried = api.post(f"/api/integrations/{failed['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["success"] is False
    case = api.get(f"/api/cases/{failed['case_id']}").json()
    assert case["status"] != "resolved"
    assert case["calendar_event_id"] is None


def test_security_case_is_flagged_and_audit_export_mentions_its_source(api):
    _as(api, "kenji.sato")
    case = _case(api, "NS-2350")
    assert case["security_flag"] is True
    assert case["priority"] == "urgent"
    _as(api, "edith.lang")
    exported = api.get("/api/audit/export", params={"export_format": "csv"})
    assert "evidence_source=audit_events" in exported.text
    pdf = api.get("/api/audit/export", params={"export_format": "pdf"})
    assert pdf.content.startswith(b"%PDF")


def test_manager_sees_department_requests_not_unrelated_it_work(api):
    _as(api, "helen.cho")
    numbers = {row["case_number"] for row in api.get("/api/cases").json()}
    assert "NS-2401" in numbers
    assert "NS-2350" not in numbers


def test_scheduling_without_a_graph_event_cannot_be_resolved(api):
    _as(api, "priya.nair")
    case = _case(api, "NS-2412")
    assert case["calendar_event_id"] is None
    _as(api, "nora.berg")
    denied = api.post(f"/api/cases/{case['id']}/resolve", json={"summary": "Pretending the meeting exists."})
    assert denied.status_code == 409
    assert denied.json()["error_code"] == "calendar_missing"


def test_successful_graph_event_stores_only_the_returned_id(tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "AAMk-real-event"})

    app = create_app(
        Settings(data_dir=tmp_path / "graph", seed=True, auth_mode="local_synthetic"),
        transport=httpx.MockTransport(handler),
    )
    with TestClient(app) as client:
        _as(client, "nora.berg")
        case = _case(client, "NS-2412")
        engine = client.app.state.engine
        actor = engine.principal_from_header("nora.berg")
        start = datetime.now(timezone.utc) + timedelta(days=2)
        result = engine.schedule_appointment(
            actor,
            case["id"],
            token="secret-token",
            start=start,
            end=start + timedelta(minutes=30),
            correlation_id="graph-success",
        )
        assert result["event_id"] == "AAMk-real-event"
        assert result["created"] is True
        assert captured["body"]["subject"].startswith("NS-2412")
        assert "secret-token" not in json.dumps(captured["body"])
        stored = client.get(f"/api/cases/{case['id']}").json()
        assert stored["calendar_event_id"] == "AAMk-real-event"
        assert stored["status"] != "resolved"
        again = engine.schedule_appointment(
            actor,
            case["id"],
            token="secret-token",
            start=start,
            end=start + timedelta(minutes=30),
            correlation_id="graph-success-2",
        )
        assert again["created"] is False
