# OpsPilot 365

OpsPilot 365 is a service-operations workspace for Northstar Operations Group, a fictional company used to demonstrate a Microsoft 365 request lifecycle.

An employee request is received, classified, routed, approved or rejected, fulfilled by a person, and closed. Every consequential change is stored as a case event and an audit event. The running application uses a local case store and a delegated Microsoft Graph client. Power Automate, Copilot Studio, Dataverse, SharePoint and Teams were **not** created in a tenant: this machine has no Power Platform CLI session and no Entra app credentials.

## What runs here

| Piece | State |
| --- | --- |
| Case model, routing, approvals, SLA, audit | Running in the Python service. Tested. |
| Local synthetic directory and Northstar cases | Seeded on an empty database. |
| Microsoft Graph client | Real HTTP calls with a delegated token. Without a token it returns `not_authenticated` and does not invent a profile, message, file or event. |
| Entra sign-in | Authorization-code flow with PKCE is implemented. It returns 503 until tenant and client ids are set. |
| Power Automate cloud flows | Specified in `power-platform/specifications/`. Not deployed. |
| Copilot Studio agent | Authoring assets in `power-platform/specifications/copilot/`. Not published. |
| Dataverse | Schema specification only. The process of record is SQLite until a solution is imported. |
| Command centre UI | React application bound to the API. |

## Run it

```powershell
cd graph-service
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m uvicorn app.main:app --port 8090

cd ..\frontend
npm install
npm run dev
```

Open http://localhost:5173. The ribbon persona control is a **local synthetic directory**, not Entra. Maya Chen is the default employee. Switch to Nora Berg or Edith Lang for operations and audit views.

Copy `.env.example` to `graph-service/.env` only when you have an app registration. Never put the client secret in the React app.

## Demonstration cases

The seed replays the policy engine. Approval decisions in that seed are stamped `local_simulation`. They are not Microsoft Approvals outcomes.

| Case | Story |
| --- | --- |
| NS-2401 | Maya's finance folder access is approved and waiting for IT fulfilment. Access is not granted by the product. |
| NS-2408 | Jonah's Excel add-in issue is in progress with Leo Marsh. |
| NS-2412 | Priya's onboarding meeting has no calendar event until Graph returns an id. |
| NS-2388 | Omar's note is too short. The case stays paused until clarification arrives. |
| NS-2310 | Lucia's facilities case is past its resolution target. One escalation is recorded. |
| NS-2419 | Pauline's collection request has a failed Graph call and is not resolved. |
| NS-2394 | Sofia's CRM export was rejected. No fulfilment task exists. |

## Repository map

- `graph-service/` — case policy, SLA calendar, audit, Graph gateway
- `frontend/` — command centre
- `power-platform/specifications/` — maker instructions, explicitly not solution exports
- `docs/` — architecture, security, flow design, licensing and test notes
- `sample-data/` — scenario catalogue

## Licence

MIT. See [LICENSE](LICENSE).
