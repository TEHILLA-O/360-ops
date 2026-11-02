"""Delegated Microsoft Graph calls.

GET requests may retry on 429 and 503. POST is not retried, so a calendar
create cannot be duplicated by the client after an ambiguous failure.
The client never synthesises a profile, message, file, or event.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings

DELEGATED_SCOPES = (
    "User.Read",
    "Mail.ReadBasic",
    "Files.Read",
    "Calendars.ReadWrite",
)


@dataclass
class GraphCall:
    ok: bool
    status: int
    error_code: str | None
    error_category: str | None
    message: str
    body: dict[str, Any] | None = None
    retry_after: int | None = None
    attempts: int = 0
    operation: str = ""
    safe_metadata: dict[str, Any] = field(default_factory=dict)


class GraphClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    def _http(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": 20.0}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def request(
        self,
        method: str,
        path: str,
        token: str | None,
        *,
        operation: str,
        json_body: dict | None = None,
    ) -> GraphCall:
        if not token or not token.strip():
            return GraphCall(
                ok=False,
                status=401,
                error_code="not_authenticated",
                error_category="human_action",
                message="No delegated Microsoft Graph token is available for this session.",
                operation=operation,
            )
        url = path if path.startswith("https://") else f"{self.settings.graph_base_url.rstrip('/')}/{path.lstrip('/')}"
        retryable = method.upper() == "GET"
        max_attempts = 3 if retryable else 1
        last = GraphCall(
            ok=False,
            status=0,
            error_code="graph_unreachable",
            error_category="retryable",
            message="Microsoft Graph was not called.",
            operation=operation,
        )
        for attempt in range(1, max_attempts + 1):
            try:
                with self._http() as client:
                    response = client.request(
                        method.upper(),
                        url,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                        json=json_body,
                    )
            except httpx.HTTPError:
                last = GraphCall(
                    ok=False,
                    status=0,
                    error_code="graph_unreachable",
                    error_category="retryable",
                    message="The Microsoft Graph endpoint could not be reached.",
                    attempts=attempt,
                    operation=operation,
                )
                if attempt < max_attempts:
                    time.sleep(min(0.2 * attempt, 1))
                    continue
                return last
            parsed = _safe_json(response)
            if response.status_code < 400:
                return GraphCall(
                    ok=True,
                    status=response.status_code,
                    error_code=None,
                    error_category=None,
                    message="Microsoft Graph accepted the request.",
                    body=parsed,
                    attempts=attempt,
                    operation=operation,
                    safe_metadata={"graph_status": response.status_code, "operation": operation},
                )
            code, text = _graph_error(parsed, response.status_code)
            category = "retryable" if response.status_code in {429, 503} else "non_retryable"
            if response.status_code in {401, 403}:
                category = "security_sensitive" if response.status_code == 403 else "human_action"
                code = "graph_access_denied" if response.status_code == 403 else "graph_token_rejected"
            retry_after = _retry_after(response)
            last = GraphCall(
                ok=False,
                status=response.status_code,
                error_code=code,
                error_category=category,
                message=text,
                retry_after=retry_after,
                attempts=attempt,
                operation=operation,
                safe_metadata={"graph_status": response.status_code, "operation": operation},
            )
            if response.status_code in {429, 503} and attempt < max_attempts:
                delay = 1 if retry_after is None else retry_after
                time.sleep(min(delay, 2))
                continue
            return last
        return last

    def get_me(self, token: str | None) -> GraphCall:
        return self.request(
            "GET",
            "/me?$select=id,displayName,mail,userPrincipalName,jobTitle,department",
            token,
            operation="graph.get_me",
        )

    def list_messages(self, token: str | None) -> GraphCall:
        return self.request(
            "GET",
            "/me/messages?$select=id,subject,receivedDateTime,isRead&$top=10",
            token,
            operation="graph.list_messages",
        )

    def list_drive_children(self, token: str | None) -> GraphCall:
        return self.request(
            "GET",
            "/me/drive/root/children?$select=id,name,size,lastModifiedDateTime&$top=20",
            token,
            operation="graph.list_drive_children",
        )

    def create_event(self, token: str | None, payload: dict) -> GraphCall:
        return self.request(
            "POST",
            "/me/events",
            token,
            operation="graph.create_event",
            json_body=payload,
        )


def _safe_json(response: httpx.Response) -> dict | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _graph_error(body: dict | None, status: int) -> tuple[str, str]:
    if not body:
        return f"graph_http_{status}", "Microsoft Graph returned an empty error response."
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = str(error.get("code") or f"graph_http_{status}")[:80]
    message = str(error.get("message") or "Microsoft Graph rejected the request.")
    message = message.replace("\n", " ")[:300]
    return code, message


def _retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None
