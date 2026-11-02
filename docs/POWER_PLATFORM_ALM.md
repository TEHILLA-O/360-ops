# Power Platform ALM

No solution has been exported or imported.

## When a development environment exists

```text
pac auth create --environment <env-url>
pac solution create --name OpsPilot365 --publisher-name Northstar --publisher-prefix op
```

Confirm the exact flags against `pac solution create --help` for the installed CLI. This machine does not have `pac`, so those flags were not executed.

Build tables, flows, variables and connection references inside the unmanaged solution. Then:

```text
pac solution export --name OpsPilot365 --path OpsPilot365.zip --managed false
pac solution unpack --zipfile OpsPilot365.zip --folder power-platform/solution
```

Commit only the files that unpack produces. Keep these specification documents beside that folder, and do not mix handwritten XML into the unpacked tree.

## Import

1. `pac solution import` into the test environment.
2. Open each connection reference and sign in.
3. Set the environment variables for that environment.
4. Turn on flows only after the mailbox and Approvals connections succeed.
5. Publish the Copilot agent only if the licence allows the channel.
6. Send one synthetic message and record the real run id.

A GitHub Actions build of this repository does not prove that a cloud flow ran.

## What not to commit

Tenant secrets, connection tokens, and a fake `solution.xml` written by hand.
