# Testing

## Python

From `graph-service` with the virtual environment:

```text
python -m ruff check app tests
python -m pytest
```

Latest local run on 2 November 2026: `ruff check` clean, **39 pytest passed**, **3 vitest passed**, and `npm run build` completed. The suite covers SLA business hours (including a holiday and a BST afternoon), classification ambiguity, routing when no team exists, illegal transitions, Graph retry policy, intake deduplication, auto-replies, unknown senders, cross-requester replies, employee isolation, rejection without fulfilment, missing managers, SLA escalation idempotency, scheduling without an event id, a successful mocked Graph create that stores only the returned id, and audit export.

Cloud flow runs, live Graph calls and Copilot Studio conversations are not marked passed. They were not executed.

`tzdata` is installed because Windows Python does not ship the IANA database that `zoneinfo` needs for `Europe/London`.

## Frontend

```text
npm run typecheck
npm test
npm run build
```

The unit test checks London formatting and that empty measures stay blank rather than becoming a zero. Playwright is not installed; browser checks were done against the Vite dev server when the UI was exercised, and that manual pass is described in the walkthrough rather than reported as an automated Playwright suite.

## What a green CI run means

The GitHub workflow runs the Python and frontend checks above. It does not authenticate to Power Platform and must not be read as evidence that OPS-01 ran in Microsoft's cloud.
