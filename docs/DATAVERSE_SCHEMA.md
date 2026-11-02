# Dataverse schema

**Status: specification.** The running store is SQLite with the same relationships. Do not import a handwritten `customizations.xml`.

Publisher prefix: `op`.

## Tables

| Table | Purpose | Notes |
| --- | --- | --- |
| `op_Request` | Authoritative case | Alternate key on case number. Alternate key on dedup key. |
| `op_RequestCategory` | Configurable policy | Required fields, approval policy, SLA minutes, resolution text. |
| `op_Requester` | Directory shadow | UPN, department, manager lookup, role. |
| `op_Assignment` | Routing evidence | Append a row per decision. Do not overwrite history. |
| `op_Approval` | Approval row | Update pending to a decision once. Further decisions are new rows. |
| `op_CaseEvent` | Workflow journal | Append only. |
| `op_Communication` | Acknowledgements and replies | Delivery status is explicit. |
| `op_DocumentReference` | SharePoint or manual reference | No file column. |
| `op_SLA` | Evaluation snapshot | Written by the watch, not edited later. |
| `op_Escalation` | One row per case and threshold | Alternate key on dedup key. |
| `op_IntegrationRun` | Flow or Graph attempt | Failed rows stay failed. A retry is a new row. |
| `op_Notification` | Intended notice | Status includes not delivered. |
| `op_AuditEvent` | Compliance journal | Append only. No user delete. |
| `op_WorkflowConfiguration` | Rule version and calendar | Current version `2026.11.0`. |

## Choice columns

**Status:** New, Awaiting information, Classified, Assigned, Awaiting approval, Approved, Rejected, In progress, Awaiting fulfilment, Resolved, Closed, Cancelled.

**Approval state:** Not required, Pending, Approved, Rejected, Cancelled, Expired, Failed.

**Priority:** Low, Normal, High, Urgent.

**Source channel:** Outlook, Web, Teams, Copilot.

**SLA state:** Healthy, Approaching deadline, Breached, Paused, Completed, Not applicable.

## Relationships

- Request → Requester (required)
- Request → Category (optional until classification)
- Assignment, Approval, Communication, Document, SLA snapshot, Escalation, Case event → Request
- Approval → Requester as approver (optional when the manager cannot be resolved)

## Concurrency

`op_Request` carries an integer version. Updates include the version in the match. A mismatch returns conflict rather than a silent overwrite.

## SharePoint-list adaptation

If Dataverse is not available, create one list per table above with the same columns and a text case-number key. Approval actions may still require Dataverse behind the Approvals connector; that does not force the case list into Dataverse. Document which list is authoritative before go-live. This repository does not create the lists.
