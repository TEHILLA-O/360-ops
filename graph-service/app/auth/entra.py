"""Authorization-code sign-in with PKCE. Tokens stay in the server process."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import msal

from app.auth.graph_client import DELEGATED_SCOPES
from app.config import Settings


@dataclass
class Session:
    id: str
    access_token: str
    account_hint: str


class EntraAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._flows: dict[str, dict] = {}
        self._sessions: dict[str, Session] = {}

    def _app(self):
        authority = f"https://login.microsoftonline.com/{self.settings.azure_tenant_id}"
        if self.settings.azure_client_secret.strip():
            return msal.ConfidentialClientApplication(
                self.settings.azure_client_id,
                authority=authority,
                client_credential=self.settings.azure_client_secret,
            )
        return msal.PublicClientApplication(self.settings.azure_client_id, authority=authority)

    def authorization_url(self) -> str:
        if not self.settings.entra_configured:
            raise RuntimeError("entra_not_configured")
        flow = self._app().initiate_auth_code_flow(
            scopes=list(DELEGATED_SCOPES),
            redirect_uri=self.settings.azure_redirect_uri,
        )
        state = flow.get("state") or secrets.token_urlsafe(24)
        flow["state"] = state
        self._flows[state] = flow
        return flow["auth_uri"]

    def complete(self, query: dict[str, str]) -> Session:
        state = query.get("state", "")
        flow = self._flows.pop(state, None)
        if flow is None:
            raise RuntimeError("signin_state_missing")
        result = self._app().acquire_token_by_auth_code_flow(flow, query)
        if "access_token" not in result:
            raise RuntimeError(result.get("error") or "token_exchange_failed")
        session = Session(
            id=secrets.token_urlsafe(32),
            access_token=result["access_token"],
            account_hint=str((result.get("id_token_claims") or {}).get("preferred_username") or ""),
        )
        self._sessions[session.id] = session
        return session

    def session_from(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def token_for(self, session_id: str | None) -> str | None:
        session = self.session_from(session_id)
        return session.access_token if session else None
