# Entra authentication

The service implements the authorization-code flow with PKCE through MSAL (`app/auth/entra.py`).

## App registration

1. Register an application in the target tenant.
2. Add a web redirect URI of `http://localhost:8090/auth/callback` for local development.
3. Enable public client only if you omit the client secret. If a secret is set, the service uses a confidential client and the secret stays in the API process.
4. Add delegated Graph permissions, and no application permissions:
   - `User.Read`
   - `Mail.ReadBasic`
   - `Files.Read`
   - `Calendars.ReadWrite`
5. Grant admin consent. `Calendars.ReadWrite` and `Mail.ReadBasic` need it in most tenants.
6. Set `OPSPILOT_AZURE_TENANT_ID`, `OPSPILOT_AZURE_CLIENT_ID`, and optionally `OPSPILOT_AZURE_CLIENT_SECRET`.
7. Set `OPSPILOT_AUTH_MODE=entra` when the local persona header must be rejected.

## What the browser receives

`/auth/login` redirects to Microsoft. `/auth/callback` stores the access token in server memory under an HttpOnly `opspilot_session` cookie and redirects to the command centre. The React app never reads the token.

Restarting the API drops in-memory sessions. That is acceptable for this development service and should be replaced with a server-side session store before any shared deployment.

## What was verified

The unconfigured login route is specified to return `entra_not_configured`. No live sign-in has been completed, because no app registration exists in this environment. Do not treat the local persona switcher as Entra.
