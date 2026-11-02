# Copilot Studio agent

**Status: not created and not published.** No Copilot Studio licence check was possible. The command-centre Copilot page is a tool runner for the local contract. It is not the agent and it does not call a general-purpose chat model.

## Agent

- **Name:** OpsPilot Assistant
- **Goal:** help an employee submit a request, supply missing detail, read approved guidance, and check the status of their own cases.
- **Instructions to paste into the agent:**
  - Answer only from tool results and the approved knowledge sources.
  - If a tool returns no case, say so. Do not guess a status.
  - If a tool returns more than one case, ask the employee to pick a case number.
  - Never say access has been granted. Approval and fulfilment are different.
  - Never promise a mailbox, team or folder permission change.
  - Do not repeat internal approval comments to the employee.
  - Escalate to the service desk when the question is sensitive or the tools fail.

## Topics

1. Create service request — collects title and description, calls OPS-AGENT-01, tells the employee the case number, and stops. Classification continues in Power Automate.
2. Check request status — calls OPS-AGENT-02 with the employee's utterance.
3. Explain required approvals — reads the category policy and, when a case number is present, the stored approval state.
4. Provide request guidance — answers from category definitions and SLA policies only.
5. Escalate to service desk — calls OPS-AGENT-04's sibling escalation action and tells the employee whether Teams delivery actually happened.

## Knowledge

Upload the category descriptions and the employee guidance from Settings, plus any SharePoint pages the service desk has marked approved. Do not point the agent at a library that contains confidential case files.

## Channels

Teams publishing depends on the Copilot Studio licence and an allowed channel. It was not published here. Keep the topic configuration even when the channel cannot be turned on.

## How to test later

Sign in as a non-admin employee. Ask for another person's case number. The tool must return no case. Ask for the employee's own finance request and compare the sentence with the Dataverse or local case row.
