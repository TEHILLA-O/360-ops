"""Request helpers kept out of main so the router can import them safely."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone

from fastapi import Request

from app.auth.graph_client import DELEGATED_SCOPES
from app.config import Settings
from app.domain.categories import CATEGORIES

SESSION_COOKIE = "opspilot_session"


def capability_report(settings: Settings) -> dict:
    return {
        "product": "OpsPilot 365",
        "assessed_from": "running_service",
        "dependencies": [
            {"name": "Python case service", "status": "available", "note": f"Python {sys.version.split()[0]} is running this process."},
            {"name": "Local case store", "status": "available", "note": "SQLite is the local authoritative store because Dataverse is not connected."},
            {"name": "Power Platform CLI", "status": "available" if shutil.which("pac") else "not_available", "note": "pac was found on PATH." if shutil.which("pac") else "pac was not found on PATH."},
            {"name": "Azure CLI", "status": "available" if shutil.which("az") else "not_available", "note": "az was found on PATH." if shutil.which("az") else "az was not found on PATH."},
            {"name": "Microsoft Entra app", "status": "requires_configuration" if not settings.entra_configured else "requires_consent", "note": "Tenant and client id are read from the environment."},
            {"name": "Microsoft Graph delegated calls", "status": "requires_configuration" if not settings.entra_configured else "untested", "note": "No profile is fabricated when a token is absent."},
            {"name": "Power Automate", "status": "not_available", "note": "No cloud flow has been created or exported."},
            {"name": "Copilot Studio", "status": "not_available", "note": "The agent is specified, not published."},
            {"name": "Dataverse", "status": "not_available", "note": "Schema is documented for import. No environment is connected."},
            {"name": "SharePoint", "status": "not_available", "note": "Document rows are references only."},
            {"name": "Microsoft Teams", "status": "not_configured" if not settings.teams_configured else "untested", "note": "Notifications stay unsent until a webhook is configured."},
        ],
        "delegated_scopes": list(DELEGATED_SCOPES),
        "categories": [item["id"] for item in CATEGORIES],
    }


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def session_token(request: Request) -> str | None:
    return request.app.state.entra.token_for(request.cookies.get(SESSION_COOKIE))


def actor_from(request: Request):
    return request.app.state.engine.principal_from_header(request.headers.get("X-OpsPilot-Actor"))
