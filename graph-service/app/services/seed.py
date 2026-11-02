"""Deterministic Northstar demonstration cases.

Every case is created through the policy engine. Approval rows created here
use decision_authority local_simulation. No Microsoft cloud call is made.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.domain.permissions import Principal
from app.domain.sla import subtract_business_minutes
from app.services.engine import SYSTEM, Engine

AGENT_TEAMS = ["IT Service Desk", "Manual Triage", "Unassigned", "Document Owners"]


def _person(person_id, name, department, title, role, manager=None, teams=None):
    return {
        "id": person_id,
        "upn": f"{person_id}@northstar.example",
        "display_name": name,
        "department": department,
        "job_title": title,
        "role": role,
        "manager_id": manager,
        "teams": teams or [],
    }


ROSTER = [
    _person("maya.chen", "Maya Chen", "Finance", "Financial analyst", "employee", "helen.cho"),
    _person("jonah.adeyemi", "Jonah Adeyemi", "Sales", "Account executive", "employee", "camille.dubois"),
    _person("priya.nair", "Priya Nair", "Human Resources", "HR coordinator", "employee", "ruth.adewale"),
    _person("omar.farouk", "Omar Farouk", "Operations", "Operations coordinator", "employee", "nora.berg"),
    _person("lucia.romero", "Lucia Romero", "Facilities", "Workplace coordinator", "employee", "patrick.nolan"),
    _person("ben.carter", "Ben Carter", "IT", "Support engineer", "employee", "samir.rahman"),
    _person("aisha.bello", "Aisha Bello", "Finance", "Management accountant", "employee", "helen.cho"),
    _person("tomislav.horvat", "Tomislav Horvat", "Sales", "Sales operations analyst", "employee", "camille.dubois"),
    _person("kenji.sato", "Kenji Sato", "IT", "Platform engineer", "employee", "samir.rahman"),
    _person("freya.lind", "Freya Lind", "Human Resources", "People partner", "employee", "ruth.adewale"),
    _person("daniel.okeke", "Daniel Okeke", "Facilities", "Facilities technician", "employee", "patrick.nolan"),
    _person("sofia.almeida", "Sofia Almeida", "Sales", "Customer operations lead", "employee", "camille.dubois"),
    _person("ingrid.solberg", "Ingrid Solberg", "Finance", "Finance business partner", "employee", "helen.cho"),
    _person("chris.holm", "Chris Holm", "Sales", "Business development manager", "employee", None),
    _person("noah.briggs", "Noah Briggs", "Operations", "Planning analyst", "employee", "nora.berg"),
    _person("imani.brooks", "Imani Brooks", "Human Resources", "HR analyst", "employee", "ruth.adewale"),
    _person("rita.osman", "Rita Osman", "Sales", "Solutions consultant", "employee", "camille.dubois"),
    _person("marcus.reid", "Marcus Reid", "Operations", "Process analyst", "employee", "nora.berg"),
    _person("pauline.vogel", "Pauline Vogel", "Operations", "Logistics coordinator", "employee", "nora.berg"),
    _person("leo.marsh", "Leo Marsh", "IT", "Service desk agent", "service_desk_agent", "samir.rahman", AGENT_TEAMS),
    _person("idris.mensah", "Idris Mensah", "IT", "Service desk agent", "service_desk_agent", "samir.rahman", AGENT_TEAMS),
    _person("helen.cho", "Helen Cho", "Finance", "Finance manager", "department_manager", "nora.berg"),
    _person("ruth.adewale", "Ruth Adewale", "Human Resources", "HR manager", "department_manager", "nora.berg"),
    _person("patrick.nolan", "Patrick Nolan", "Facilities", "Facilities manager", "department_manager", "nora.berg"),
    _person("camille.dubois", "Camille Dubois", "Sales", "Sales director", "department_manager", "nora.berg"),
    _person("samir.rahman", "Samir Rahman", "IT", "IT administrator", "administrator", "nora.berg"),
    _person("nora.berg", "Nora Berg", "Operations", "Operations manager", "operations_manager", None),
    _person("edith.lang", "Edith Lang", "Compliance", "Assurance reviewer", "auditor", "nora.berg"),
    _person("grace.elliott", "Grace Elliott", "Operations", "Operations administrator", "administrator", "nora.berg"),
]


def _principal(person_id: str) -> Principal:
    person = next(item for item in ROSTER if item["id"] == person_id)
    return Principal(
        id=person["id"],
        display_name=person["display_name"],
        role=person["role"],
        department=person["department"],
        teams=tuple(person["teams"]),
        upn=person["upn"],
    )


def run_seed(engine: Engine) -> None:
    with engine.store.session() as conn:
        for person in ROSTER:
            engine.store.upsert_requester(conn, person)
    now = engine.clock.now()
    leo = _principal("leo.marsh")
    patrick = _principal("patrick.nolan")
    samir = _principal("samir.rahman")

    def cid() -> str:
        return str(uuid.uuid4())

    def mail(sender, subject, body, message_id, when, number, process=True):
        return engine.ingest_message(
            SYSTEM,
            {
                "mailbox": engine.settings.support_mailbox,
                "message_id": message_id,
                "subject": subject,
                "body": body,
                "sender_upn": f"{sender}@northstar.example",
                "headers": {},
            },
            process=process,
            correlation_id=cid(),
            at=when,
            explicit_number=number,
        )

    maya = mail(
        "maya.chen",
        "Finance folder access request",
        "Please grant access to the finance reporting library.\n"
        "Resource: Finance Reporting library\n"
        "Justification: I need the monthly close pack for the operations commentary.",
        "msg-2401",
        now - timedelta(days=4),
        "NS-2401",
    )
    engine.record_simulated_decision(
        SYSTEM,
        _pending_approval(engine, maya["case_id"]),
        "approved",
        "Local simulation: the finance manager approves the request. This is not a Microsoft Approvals decision.",
        cid(),
        at=now - timedelta(days=4) + timedelta(hours=2),
    )
    engine.ingest_message(
        SYSTEM,
        {
            "mailbox": engine.settings.support_mailbox,
            "message_id": "msg-2401",
            "subject": "Finance folder access request",
            "body": "duplicate delivery",
            "sender_upn": "maya.chen@northstar.example",
            "headers": {},
        },
        process=True,
        correlation_id=cid(),
        at=now - timedelta(days=4, minutes=-5),
    )

    jonah = mail(
        "jonah.adeyemi",
        "Excel add-in crash",
        "The forecasting add-in closes Excel whenever I refresh a workbook on the sales laptop.",
        "msg-2408",
        now - timedelta(days=1, hours=3),
        "NS-2408",
    )
    engine.accept_work(leo, jonah["case_id"], cid(), at=now - timedelta(days=1, hours=2))

    mail(
        "priya.nair",
        "Book onboarding session",
        "Please book an onboarding meeting for Imani Brooks.\nWindow: Tuesday morning next week",
        "msg-2412",
        now - timedelta(days=1),
        "NS-2412",
    )

    mail(
        "omar.farouk",
        "Help",
        "Need help",
        "msg-2388",
        now - timedelta(hours=6),
        "NS-2388",
    )

    lucia_when = now - timedelta(days=18)
    lucia = mail(
        "lucia.romero",
        "HVAC noise on level 4",
        "The air handling unit above the east studio is loud enough to stop conversation.",
        "msg-2310",
        lucia_when,
        "NS-2310",
    )
    engine.accept_work(patrick, lucia["case_id"], cid(), at=lucia_when + timedelta(hours=5))

    pauline = mail(
        "pauline.vogel",
        "Schedule equipment collection",
        "Please schedule collection of the spare monitors from the operations floor.\nWindow: Thursday afternoon",
        "msg-2419",
        now - timedelta(days=2),
        "NS-2419",
    )
    engine.schedule_appointment(
        SYSTEM,
        pauline["case_id"],
        token=None,
        start=now + timedelta(days=1),
        end=now + timedelta(days=1, minutes=30),
        correlation_id=cid(),
    )

    sofia = mail(
        "sofia.almeida",
        "CRM export access request",
        "I need a copy of the customer extract.\n"
        "Resource: CRM export folder\n"
        "Justification: I want a personal offline copy of all customer records.",
        "msg-2394",
        now - timedelta(days=3),
        "NS-2394",
    )
    engine.record_simulated_decision(
        SYSTEM,
        _pending_approval(engine, sofia["case_id"]),
        "rejected",
        "Local simulation: bulk customer exports are outside policy. No fulfilment task should be created.",
        cid(),
        at=now - timedelta(days=3) + timedelta(hours=4),
    )

    mail(
        "ben.carter",
        "New laptop request sitting in the mailbox",
        "The new starter laptop for the design seat has not been imaged.",
        "msg-2422",
        now - timedelta(minutes=20),
        "NS-2422",
        process=False,
    )

    aisha_submitted = now - timedelta(days=2)
    aisha = mail(
        "aisha.bello",
        "Travel policy document",
        "Please send the current travel policy document for the November close.",
        "msg-2370",
        aisha_submitted,
        "NS-2370",
    )
    engine.accept_work(leo, aisha["case_id"], cid(), at=aisha_submitted + timedelta(hours=1))
    engine.resolve_case(
        leo,
        aisha["case_id"],
        "The approved travel policy link was recorded for Aisha. No file bytes were copied.",
        cid(),
        at=now - timedelta(seconds=5),
    )

    mail(
        "tomislav.horvat",
        "Sales team membership request",
        "Please add me to the pricing team.\nResource: Pricing Team\nJustification: I cover renewals while Camille is travelling.",
        "msg-2366",
        now - timedelta(hours=8),
        "NS-2366",
    )

    mail(
        "kenji.sato",
        "Account locked after phishing report",
        "I am locked out of my account after reporting a phishing message and I cannot log in.",
        "msg-2350",
        now - timedelta(hours=2),
        "NS-2350",
    )

    freya_at = now - timedelta(days=6)
    freya = mail(
        "freya.lind",
        "Onboarding form request",
        "Please send the current starter checklist form.",
        "msg-2333",
        freya_at,
        "NS-2333",
    )
    engine.accept_work(leo, freya["case_id"], cid(), at=freya_at + timedelta(hours=2))
    engine.resolve_case(leo, freya["case_id"], "Checklist reference recorded.", cid(), at=freya_at + timedelta(days=1))
    engine.reopen_case(leo, freya["case_id"], "The checklist version was superseded.", cid(), at=now - timedelta(days=1))

    daniel = mail(
        "daniel.okeke",
        "Replace the cracked reception desk",
        "The reception desk top is cracked and needs replacement.",
        "msg-2320",
        now - timedelta(days=2, hours=2),
        "NS-2320",
    )
    engine.accept_work(patrick, daniel["case_id"], cid(), at=now - timedelta(days=2))

    mail(
        "marcus.reid",
        "Access and a laptop",
        "I need access to the facilities maintenance folder and a laptop for the night roster.",
        "msg-2415",
        now - timedelta(hours=5),
        "NS-2415",
    )

    ingrid_at = now - timedelta(days=12)
    ingrid = mail(
        "ingrid.solberg",
        "Management accounts library access",
        "Resource: Management accounts library\nJustification: Quarter-end commentary for the board pack.",
        "msg-2290",
        ingrid_at,
        "NS-2290",
    )
    engine.record_simulated_decision(
        SYSTEM,
        _pending_approval(engine, ingrid["case_id"]),
        "approved",
        "Local simulation of an earlier finance approval.",
        cid(),
        at=ingrid_at + timedelta(hours=3),
    )
    engine.record_fulfilment(
        samir,
        ingrid["case_id"],
        "An administrator changed the library membership outside OpsPilot and recorded that verification here.",
        cid(),
        at=ingrid_at + timedelta(days=1),
    )
    engine.close_case(SYSTEM, ingrid["case_id"], "Verification reviewed and the case closed.", cid(), at=ingrid_at + timedelta(days=2))

    mail(
        "chris.holm",
        "Proposal archive access",
        "Resource: Proposal archive\nJustification: I need last year's renewal deck.",
        "msg-2404",
        now - timedelta(days=1, hours=4),
        "NS-2404",
    )

    noah = mail(
        "noah.briggs",
        "General planning question",
        "Please point me to the owner of the capacity planning workbook.",
        "msg-2301",
        now - timedelta(days=5),
        "NS-2301",
    )
    engine.cancel_case(SYSTEM, noah["case_id"], "The requester withdrew the question.", cid(), at=now - timedelta(days=4, hours=20))

    approaching_at = subtract_business_minutes(now, 1080, engine.calendar)
    rita = mail(
        "rita.osman",
        "VPN disconnects on the sales laptop",
        "The VPN drops every few minutes during customer calls.",
        "msg-2425",
        approaching_at,
        "NS-2425",
    )
    engine.accept_work(leo, rita["case_id"], cid(), at=approaching_at + timedelta(minutes=30))

    engine.add_document_reference(
        SYSTEM,
        maya["case_id"],
        filename="close-pack-justification.txt",
        doc_type="note",
        source="synthetic_seed",
        correlation_id=cid(),
    )
    engine.sweep_sla(SYSTEM)


def _pending_approval(engine: Engine, case_id: str) -> str:
    rows = [row for row in engine.store.list_where("approvals", "case_id", case_id) if row["state"] == "pending"]
    if not rows:
        raise RuntimeError(f"No pending approval for {case_id}")
    return rows[-1]["id"]
