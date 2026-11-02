# Security

This is a development design, not a compliance certification.

## Roles

| Role | Can read | Can change |
| --- | --- | --- |
| Employee | Own cases | Submit, clarify own case, cancel only while new or awaiting information |
| Service desk agent | Assigned teams, unassigned, cases they own | Accept, classify, resolve non-access work |
| Department manager | Their department, their approvals | Accept department work |
| Operations manager | All operational cases | Route, sweep SLA, retry safe integrations |
| Administrator | All cases | Simulated approval, verified fulfilment, configuration probes |
| Auditor | All cases and audit | Export only |

Checks run in the service. The React persona header is honoured only in `local_synthetic` mode.

## Least privilege

Graph scopes are the four delegated scopes in `GRAPH_API.md`. The assistant cannot receive an arbitrary Graph URL. Scheduling creates an event on the signed-in user's calendar only.

## Secrets

Client secrets and tokens are server-side. Logs redact bearer tokens, `client_secret`, `sig` and `access_token` query values. Audit metadata stores message length and ids, not the raw body, for intake. Case descriptions remain on the case because agents have to read them.

## Sensitive actions

SharePoint permission changes are out of scope for the MVP. Fulfilment records a human verification. Rejected and pending approvals cannot be fulfilled. Graph failures do not mark a case resolved.

## Known limits

- Local mode is a demonstration control. Turn on Entra mode before any shared use.
- Sessions are in memory.
- SQLite is a single-node store without customer-managed keys.
- Read access is enforced on each query. Successful reads are not copied into the audit log; denied reads, exports, decisions and integration attempts are.
