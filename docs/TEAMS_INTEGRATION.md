# Teams integration

Teams is not connected.

When `OPSPILOT_TEAMS_WEBHOOK_URL` is empty, every intended Teams notice is stored in `notifications` with status `not_delivered_channel_unconfigured`. The summary contains the case number and a short operational sentence. It does not contain the request description.

Notices the engine knows how to record:

- routing failed
- security language on a new case
- approval requested
- approval failed or rejected
- SLA warning and escalation
- assistant escalation

If a webhook is set later, the service posts `{"text": summary}` and stores `delivered` or `failed` from the HTTP result. That has not been tested with a real webhook.

Interactive adaptive-card approvals are not implemented. A card response would not be treated as an authenticated approval. OPS-04 uses the Approvals connector for that, once the flow exists.

The Copilot Studio Teams channel was not published.
