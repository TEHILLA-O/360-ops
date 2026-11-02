# Architecture

OpsPilot keeps the business process visible as Power Automate designs and keeps a testable policy engine beside them. The engine is the local stand-in. It is not a substitute that pretends a cloud flow ran.

```text
Outlook / web form / assistant tool
        |
        v
OPS-01 intake  -->  case row + acknowledgement record
        |
        v
OPS-02 classify --> allowed category, or manual triage
        |
        v
OPS-03 route    --> team, rule id, rule version, or unassigned
        |
        +--> OPS-04 approval, when the category requires it
        +--> OPS-05 calendar, only after Graph returns an event id
        |
        v
OPS-06 SLA watch --> one escalation per case and threshold
        |
        v
audit_events (append only) and the command centre
```

## Boundaries

- **Authoritative local store.** SQLite tables mirror the requested case, approval, assignment, communication, document reference, SLA, escalation, integration and audit records. Dataverse is the intended enterprise store and is specified, not connected.
- **Policy engine.** Classification, routing, transitions, deduplication and SLA arithmetic live in `graph-service/app/domain`. The API refuses illegal transitions.
- **Graph gateway.** `GraphClient` calls `/me`, `/me/messages`, `/me/drive/root/children` and `POST /me/events` with a delegated token. GET may retry 429 and 503. POST is not retried. Application permissions are not requested.
- **Assistant tools.** `/api/assistant/*` returns a fixed JSON contract (`success`, `case_id`, `case_number`, `status`, `message`, `next_action`, `updated_at`, `error_code`). Messages are rendered from stored fields.
- **Cloud flows.** Documented only. Integration rows use `source = local_policy_engine` or `source = graph`. `source = power_automate` is reserved for a callback that is not enabled.

## Identity

`OPSPILOT_AUTH_MODE=local_synthetic` trusts the `X-OpsPilot-Actor` header and only for ids present in the seeded directory. `policy.engine` is not a selectable user. When the mode is `entra`, that header is rejected.

Employees see their own cases. A known case number for someone else returns 404, and the attempt is audited.
