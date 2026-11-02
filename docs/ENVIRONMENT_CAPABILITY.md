# Environment capability assessment

Assessed on 2 November 2026 on the development machine used to build this repository. Status words mean what was observed, not what a future tenant might allow.

| Dependency | Status | Evidence |
| --- | --- | --- |
| Python 3.12.10 | Available, tested | `python --version` succeeded. The case service test suite runs on it. |
| Node.js v23.6.1 and npm 11.0.0 | Available, tested | Version commands succeeded. |
| .NET SDK 10.0.300 | Available, tested | `dotnet --version` succeeded. |
| Power Platform CLI (`pac`) | Not available | `pac` is not on PATH. No `pac auth` or solution export was attempted. |
| Azure CLI | Not available | `az` is not on PATH. |
| `.env` / Graph credentials | Not configured | No `.env` file was present. Tenant id and client id are empty. |
| Microsoft 365 tenant | Not available | No organisational or developer-tenant session was present. |
| Power Automate | Not available | No environment, connection or flow was created. |
| Copilot Studio | Not available | No agent was created or published. Publishing was not tested. |
| Dataverse | Not available | No environment URL or solution was reachable. |
| SharePoint site | Not available | No site URL is configured. |
| Microsoft Teams | Not configured | No webhook or team id is set. Notifications are stored as undelivered. |
| Entra app registration | Requires configuration | The authorization-code handler exists and refuses to start without a tenant and client id. |
| Graph delegated call | Untested against a live user | The client is covered with a mock transport. A live `/me` call has not been made. |
| Connector licences | Untested | No tenant was available to inspect licences. |

The fallback in the project brief applies: the typed case model, Graph integration service, local synthetic adapter, flow specifications and configuration guidance are in the repo. Cloud integrations are pending.

A personal Microsoft account was not used, and no developer sandbox was assumed.
