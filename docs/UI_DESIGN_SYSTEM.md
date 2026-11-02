# UI design system

The command centre is a graphite ribbon on warm paper. It is an operations desk, not a generic administration shell.

## Colour

Colour marks state. Cobalt is the working accent. Teal is a healthy or completed SLA. Amber is a pause, a warning, or a simulated approval. Coral is a breach or a failed call. Slate is secondary text. Large gradients, glass panels and neon are intentionally absent.

## Type

IBM Plex Sans for text. IBM Plex Mono for case numbers, counts, timestamps and durations, with tabular figures.

## Navigation

Workspaces sit in a horizontal strip under the ribbon: Command, Caseflow, Approvals, Copilot, Automation, Connections, Documents, Intelligence, Audit, Settings. There is no persistent left sidebar.

Ctrl+K opens the command palette for workspaces and visible cases.

A status line under the ribbon states that the persona is local and that Graph, Power Automate and Copilot Studio are not connected. That line is part of the product, because hiding it would overstate the integration.

## Motion

The palette and hover states are the motion. `prefers-reduced-motion: reduce` disables animation.

## Case inspection

Selecting a case opens an inspector beside the register. Status changes go to the API. The page does not paint a stage complete on its own.

## Copilot page

The page runs the assistant HTTP tools and prints the returned message and case number. It is labelled as the tool contract, not as a Copilot Studio transcript.
