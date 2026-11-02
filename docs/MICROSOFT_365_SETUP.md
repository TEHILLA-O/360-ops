# Microsoft 365 setup

Nothing in this list has been executed against a tenant.

## 1. Tenant

Use a Microsoft 365 developer sandbox or an authorised non-production tenant. Do not create the demonstration people as real accounts in production. The seeded roster uses `@northstar.example`.

## 2. Power Platform environment

1. Create or select a development environment with Dataverse if you want the preferred store. A SharePoint-list adaptation is documented in `DATAVERSE_SCHEMA.md` if Dataverse is not licensed.
2. Create publisher prefix `op` and unmanaged solution `OpsPilot365`.
3. Add the environment variables and connection references in `power-platform/specifications/README.md`.
4. Create a service mailbox, for example `servicedesk@<tenant>`, and put it in `op_SupportMailbox`.
5. Create a SharePoint site for case document references. Grant access through normal SharePoint groups. OpsPilot stores links, it does not re-host files.

## 3. Mail and Teams

- Outlook connector on the service mailbox, not on a personal mailbox.
- Teams notifications should go to a private operations channel. Do not post request descriptions to a broad team.
- Approvals use the standard Approvals connector. The custom UI must not be treated as the approval itself.

## 4. After import

Re-authorise every connection reference, set environment variables, turn on the flows, and run one synthetic message through OPS-01. Record the flow run id. Until that run exists, the command centre correctly shows zero cloud runs.
