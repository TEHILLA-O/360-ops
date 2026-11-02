# Copilot agent tools

These are the contracts OPS-AGENT flows should return. The local routes already implement them. A Copilot topic should map tool outputs onto these fields and should not pass raw exception text to the employee.

## OPS-AGENT-01 | Create Case

- **Trigger:** Copilot tool action, synchronous.
- **Input:** `title`, `description`, optional `resource_name`, `justification`, `preferred_window`. The requester is the signed-in user.
- **Response:**

```json
{
  "success": true,
  "case_id": "uuid",
  "case_number": "NS-3000",
  "status": "assigned",
  "message": "sentence built from the stored case",
  "next_action": "what happens next",
  "updated_at": "timestamp",
  "error_code": null
}
```

- **Timeout:** return as soon as the case row exists. Do not wait for manager approval.

## OPS-AGENT-02 | Get Case Status

- **Input:** `text` such as "What's happening with my finance access request?"
- **Behaviour:** search only cases the caller can read. One match returns the stored status sentence. Several matches return `error_code: ambiguous` and candidates of case number, title and status. No match returns `error_code: no_match` and a null case id.
- **Local route:** `POST /api/assistant/status`.

## OPS-AGENT-03 | Get My Open Requests

- **Input:** none beyond the caller.
- **Response:** `requests[]` with case id, number, title, status and approval state. Closed, resolved and cancelled rows are omitted.
- **Local route:** `POST /api/assistant/my-requests`.

## OPS-AGENT-04 | Submit Clarification

- **Input:** `case_id`, `text`.
- **Behaviour:** only the requester, or a service role working that case, may append text. The engine reclassifies. Employees cannot target another person's case; the API returns 404.
- **Local route:** `POST /api/assistant/clarification?case_id=`.

## Related routes

- `POST /api/assistant/explain-approval`
- `POST /api/assistant/guidance`
- `POST /api/assistant/escalate` — records the question and sets delivery to `not_delivered_channel_unconfigured` unless Teams is configured.

## Failure behaviour

Tool failures return `success: false` or a structured `error_code` and a short `message`. They do not include stack traces, tokens or other employees' descriptions.
