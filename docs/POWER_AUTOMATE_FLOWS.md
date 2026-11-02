# Power Automate flows

**Status: not deployed.** No flow was created, run, or exported. The steps below are the design a maker enters in the cloud-flow designer. Expressions are guidance, not a claim that a definition exists.

Local policy-engine rows in the API use the same flow names so the observatory can show rehearsal activity. Those rows are labelled `local_policy_engine`. They are not Power Automate run history.

Shared failure behaviour for every flow:

- Wrap external actions in a Scope.
- Configure run-after on a parallel Scope for failure, timeout and skip.
- Write an `op_IntegrationRun` row with outcome `failed`, an error category, a correlation id and the case id.
- Never set the case to resolved inside a failure branch.

Connection references are listed in `power-platform/specifications/README.md`.

## OPS-01 | Outlook Request Intake

- **Trigger:** Office 365 Outlook, "When a new email arrives (V3)", folder Inbox, on the mailbox in `op_SupportMailbox`.
- **Inputs:** message id, conversation id, from address, subject, body preview or body, Internet message headers.
- **Actions:**
  1. Condition: `to` or mailbox equals `op_SupportMailbox`. Else terminate as `wrong_mailbox` (non-retryable).
  2. Condition: header `Auto-Submitted` is `no` or empty, and the subject does not start with "Automatic reply" or "Out of office". Else terminate as suppressed.
  3. Look up the sender in `op_Requester` by user principal name. If missing, write an audit row and stop. Do not create a requester.
  4. If the subject contains `NS-` plus digits, load that case. If the requester differs, write `access_denied` and stop without saving the body on the other case. If the requester matches, append `op_Communication` and stop.
  5. Compute dedup key `mailbox|message id`. If an `op_Request` already has it, append a `duplicate_suppressed` event and stop.
  6. Create `op_Request` in status `new`, plus `request_received` audit, plus an acknowledgement email that contains only the case number, title, received time and a sign-in instruction.
- **Outputs:** case id, case number, correlation id.
- **Failure paths:** Dataverse timeout is retryable. Wrong mailbox and unknown sender are not.
- **Permissions:** the flow connection must be allowed to read the support mailbox and send as that mailbox.

## OPS-02 | Request Classification

- **Trigger:** when OPS-01 completes, or a Dataverse row is created. Pass case id, subject, body and the allowed category list. Do not let the model invent categories.
- **Actions:** call the Copilot Studio tool or an AI Builder prompt that must return category, priority, missing information, confidence and a reason. If confidence is low or the category is not in the list, set manual triage and do not claim a category. Apply the category approval floor afterwards. Security phrases set priority `urgent` but do not remove a mandatory approval.
- **Outputs:** category, confidence, missing fields.
- **Failure:** on model or tool failure, leave the case `new`, record `classify.case` as failed and human-action, and assign Manual Triage.

## OPS-03 | Assignment and Routing

- **Trigger:** after a confident classification, or when a person sets the category.
- **Actions:** evaluate the versioned rules in `app/domain/routing.py` (keep the flow expression table identical to rule version `2026.11.0`). Insert `op_Assignment` with rule id, version, team and reason. If no rule matches, leave the team empty, notify the operations administrator, and do not pick a person.
- **Outputs:** team, owning department, outcome `assigned` or `failed`.

## OPS-04 | Manager Approval

- **Trigger:** category approval policy is `required`, required fields are present, and the case is not in manual triage.
- **Actions:**
  1. Office 365 Users "Get manager (V2)" for the requester. If the manager is empty or is the requester, set approval state `failed` and stop.
  2. Create an Approvals action of type Approve/Reject. Store the approval id on `op_Approval`.
  3. Wait for the approval. On the outcome, set the case to `approved` or `rejected` and write the approval id, comments, time and flow run id.
  4. If approved and the category needs fulfilment, create an IT or scheduling fulfilment assignment. Do not change SharePoint permissions.
  5. If rejected, do not create a fulfilment assignment.
- **Failure:** approval timeout sets state `expired`. A connector failure sets `failed` and does not mark the case approved.
- **Permissions:** Approvals connector plus the Users connector. An email reply is not an approval.

## OPS-05 | Schedule Service Appointment

- **Trigger:** a scheduling case accepted by operations, after the requester confirms a window.
- **Actions:** create the event through the Graph service `POST /api/cases/{id}/schedule` so the event is created as the signed-in organiser, or use the Outlook "Create event (V4)" action. Persist the event id only from the action output. If the action fails, leave `calendar_event_id` empty and do not resolve the case.
- **Idempotency:** if an event id is already stored, do not create another.
- **Permissions:** `Calendars.ReadWrite` delegated, or the Outlook connector for the organiser's mailbox.

## OPS-06 | SLA Watch

- **Trigger:** recurrence every 15 minutes during the operations window.
- **Actions:** for each open case, compute business minutes with the Europe/London calendar and pause intervals while status is `awaiting_information`. If the state is `approaching` or `breached`, insert `op_Escalation` with dedup key `{case}|resolution|{state}`. The unique key stops a second alert on the next recurrence. Notify Teams or Outlook with case number, status and team, not the description.
- **Failure:** a notification failure stays on the escalation row as not delivered. It does not clear the breach.

## Agent flows

`OPS-AGENT-01` through `OPS-AGENT-04` are short flows with the Copilot "Run a flow from Copilot" trigger. They call the same service contracts as `/api/assistant/*` and return the JSON fields in `COPILOT_AGENT_TOOLS.md`. They must not wait on OPS-04.

## Callback that is deliberately disabled

`POST` recording of a Power Automate decision exists in the engine as `record_power_automate_decision` and always returns `power_automate_not_connected`. Enable it only when the flow presents a run id that the service can verify.
