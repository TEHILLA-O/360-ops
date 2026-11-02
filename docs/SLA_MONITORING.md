# SLA monitoring

Northstar hours are 08:00–17:30, Monday to Friday, Europe/London, skipping the holiday dates in `app/domain/calendar.py`.

Elapsed minutes are the overlap of the interval with those open hours, minus time spent in `awaiting_information`. They are not the raw difference of two timestamps. Tests cover an overnight gap, a weekend, the 2026 Christmas closure, a pause, and a British Summer Time afternoon.

## Targets

Resolution targets, in business minutes, by priority: urgent 240, high 480, normal 1140, low 2850. First-response targets are 30, 60, 240 and 480. Access requests have a priority floor of high, so the classifier cannot leave them at normal.

## States

- **breached** — elapsed business minutes have reached the target, including after the case was later resolved late
- **paused** — currently awaiting information and not already breached
- **approaching** — remaining time is within 60 minutes or 20 percent of the target, whichever is larger
- **healthy** — inside the target and not paused
- **completed** — resolved or closed inside the target
- **not applicable** — cancelled, or no category target and not paused

The clock stops at `completed_at` for terminal cases.

## Watch

`POST /api/sla/sweep` is the local rehearsal of OPS-06. It writes a snapshot and, once per case and threshold, an escalation plus an undelivered Teams notification. A second sweep does not create another escalation for the same key. NS-2310 is the seeded breach.

No Power Automate recurrence has been turned on, so the product does not claim a cloud escalation ran.
