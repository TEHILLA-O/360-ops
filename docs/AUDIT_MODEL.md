# Audit model

`audit_events` is append-only. The store has no update or delete method for it. Case changes add a new event with the previous state, the new state, the actor, the source system, the reason and a correlation id.

## Events the engine writes

Request received, duplicate suppressed, thread appended, access denied, classified, routed, routing failed, clarification requested and submitted, approval requested and recorded, work accepted, fulfilment opened, case resolved, case closed, case reopened, case cancelled, calendar event created or failed, SLA warning, escalation, document attached, assistant escalated, audit exported.

Integration rows are separate and are not rewritten when a later attempt succeeds.

## Reconstruction

Open a case in Caseflow. The journey is the event list in time order. For NS-2401 that includes receipt, classification, routing, the approval request, the simulated approval, and the fulfilment assignment. The approval row still says `local_simulation`, so an auditor can see the decision was not a Microsoft Approvals result.

## Export

Auditors, administrators and operations managers can download CSV, JSON or PDF. The export states the generation time and `evidence_source=audit_events`. The export itself is audited. Employees receive 403.

## Sensitive content

Intake audit metadata keeps the message id and body length. It does not keep the message body. Tokens are not written to the audit.
