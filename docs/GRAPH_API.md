# Microsoft Graph

The client is `graph-service/app/auth/graph_client.py`. It calls Microsoft Graph only with a delegated bearer token.

| Operation | Graph request | Scope |
| --- | --- | --- |
| Profile | `GET /me?$select=id,displayName,mail,userPrincipalName,jobTitle,department` | `User.Read` |
| Mail metadata | `GET /me/messages?$select=id,subject,receivedDateTime,isRead&$top=10` | `Mail.ReadBasic` |
| Files | `GET /me/drive/root/children?$select=id,name,size,lastModifiedDateTime&$top=20` | `Files.Read` |
| Calendar | `POST /me/events` | `Calendars.ReadWrite` |

`/me` is never called with an application-only token. The support mailbox is ingested by the Outlook connector in OPS-01, not by reading another user's mailbox.

## Behaviour that was tested

- No token: `not_authenticated`, no body, zero HTTP attempts.
- GET 429 then 200: one retry, body returned from Graph.
- POST 429: no retry, so a calendar create cannot be duplicated by the client.
- 403: `graph_access_denied`, message truncated, token not copied into the message.

A live call with a real user has not been made.

## Case scheduling

`schedule_appointment` posts to `/me/events` for the signed-in user. The case stores `calendar_event_id` only when the response JSON contains `id`. A second call returns the stored id and does not post again. Resolving a scheduling case without that id returns `calendar_missing`.

The connection-probe route `POST /api/graph/events` can create a short event titled "OpsPilot 365 connection probe" on the signed-in user's calendar. It does not update a case. Without a session it returns the Graph error and no invented event id.
