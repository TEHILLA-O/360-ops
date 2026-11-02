# Specifications — not a Power Platform export

These files are human-authored maker instructions.

They are not the output of `pac solution export`, `pac solution unpack`, or the Copilot Studio export. No solution zip, workflow.json, or Dataverse customization XML is included, because those files would look like Microsoft-generated artifacts and none were produced.

When a tenant is available:

1. Install the Power Platform CLI and run `pac auth create`.
2. Create an unmanaged solution named `OpsPilot365` with publisher prefix `op`.
3. Build the tables in [DATAVERSE_SCHEMA.md](../../docs/DATAVERSE_SCHEMA.md).
4. Build each cloud flow in [POWER_AUTOMATE_FLOWS.md](../../docs/POWER_AUTOMATE_FLOWS.md) using the connection references below.
5. Author the agent from [COPILOT_STUDIO_AGENT.md](../../docs/COPILOT_STUDIO_AGENT.md).
6. Export with `pac solution export` and only then commit the unpacked Microsoft files.

## Environment variables to create

| Schema name | Purpose |
| --- | --- |
| `op_SupportMailbox` | Mailbox watched by OPS-01 |
| `op_SharePointSiteUrl` | Site for case document references |
| `op_TeamsNotificationTarget` | Channel or webhook used for non-confidential notices |
| `op_GraphServiceBaseUrl` | Base URL of this FastAPI service |
| `op_SlaTimezone` | `Europe/London` for Northstar |
| `op_EnvironmentName` | Display name shown to makers |

Do not store client secrets in environment-variable default values that get exported.

## Connection references to create

| Reference | Connector |
| --- | --- |
| `op_sharedoffice365` | Office 365 Outlook |
| `op_sharedoffice365users` | Office 365 Users |
| `op_sharedapprovals` | Approvals |
| `op_sharedteams` | Microsoft Teams |
| `op_sharedsharepointonline` | SharePoint |
| `op_shareddataverse` | Microsoft Dataverse |

The Python service is not a connector. Call it with an HTTP action using a base URL environment variable, and keep the Entra secret in a secure flow input or Azure Key Vault, not in the exported definition.
