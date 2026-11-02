# Demonstration walkthrough

Start the API on port 8090 and the Vite app on port 5173. Port 8080 is reserved on some Windows machines (WinError 10013), so local development uses 8090. Leave the persona on Maya Chen.

1. **Command.** The lifecycle counts are cases Maya is allowed to see, not the whole company. Open cases, approvals and breaches in the strip come from `GET /api/command`.
2. **Caseflow.** Open NS-2401. The sentence says the finance folder request is approved and awaiting fulfilment by the IT Service Desk. The amber note says the decision is a local simulation. The journey lists the real event timestamps.
3. **Someone else's case.** Maya cannot open Sofia's NS-2394. The API returns 404. Switch to Edith Lang and the audit contains `access_denied`.
4. **Rejection.** As Sofia, NS-2394 is rejected and the assignments never include the IT fulfilment queue.
5. **Missing detail.** As Omar, NS-2388 is awaiting information and the SLA is paused. Submit a clarification that names the facilities problem and the case leaves that status.
6. **Breach.** As Lucia, NS-2310 is breached and has one escalation. Nora can run SLA watch again; Lucia's case is not escalated a second time.
7. **Graph.** As Pauline, NS-2419 has a failed `graph.create_event` and no event id. Employees cannot run connection probes. As Grace Elliott or Nora Berg, Connections → Probe Graph profile returns `not_authenticated` and a null profile until Entra sign-in exists.
8. **Copilot page.** Ask "What's happening with my finance access request?" as Maya. The answer's case number is NS-2401 and the status matches the case. Asking for NS-2394 returns no case.
9. **Intelligence.** Maya is refused. Edith or Nora sees rates computed from the store, a bottleneck sentence only when waiting time exists, and zero Power Automate runs.
10. **Audit.** Edith can download CSV, JSON and PDF. The file header names `audit_events`.

Switch personas from the ribbon. The directory is synthetic. Do not describe this walkthrough as a production tenant test.
