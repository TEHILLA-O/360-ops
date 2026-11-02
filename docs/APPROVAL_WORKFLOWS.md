# Approval workflows

Access requests require a manager decision. The classifier cannot waive that.

## Integrity

An approval row stores the case, the approver, the requested action, the decision, the time, comments, the authority and the correlation id.

`decision_authority` is one of:

- `pending` — no decision yet, and Microsoft Approvals has not been started in this environment
- `local_simulation` — an administrator or the seed recorded a decision for the demonstration
- `power_automate` — reserved. The callback currently returns 503 and writes nothing

The command centre shows a banner when a decision was simulated.

## Self-approval

If the recorded manager is the requester, the engine sets `self_approval_blocked` and does not open an approval the requester can complete.

## Missing manager

The case stays assigned to the department queue, `approval_state` becomes `failed`, and `blocking_reason` is `missing_manager`. No employee is invented to fill the gap.

## Fulfilment

An approved access request moves to `awaiting_fulfilment` on the IT Service Desk. `record_fulfilment` is limited to an administrator, requires `approval_state = approved`, and writes `access_granted_by_opspilot: false`. The administrator is recording that a change was made through the normal administrative process.

A rejected request cannot be fulfilled. The test `test_rejection_does_not_open_fulfilment` covers NS-2394.

## What the employee sees

Approval comments are removed from employee payloads. The status sentence for NS-2401 is built from the title, the approval state and the fulfilment team.
