"""Documented workflow catalogue.

`deployed` is false until a real Power Automate or Copilot Studio asset exists
in a tenant. Local policy runs are counted separately and are not cloud runs.
"""

from __future__ import annotations

FLOWS = (
    {
        "id": "OPS-01",
        "name": "OPS-01 | Outlook Request Intake",
        "kind": "power_automate_cloud_flow",
        "deployed": False,
        "depends_on": [],
    },
    {
        "id": "OPS-02",
        "name": "OPS-02 | Request Classification",
        "kind": "power_automate_cloud_flow",
        "deployed": False,
        "depends_on": ["OPS-01"],
    },
    {
        "id": "OPS-03",
        "name": "OPS-03 | Assignment and Routing",
        "kind": "power_automate_cloud_flow",
        "deployed": False,
        "depends_on": ["OPS-02"],
    },
    {
        "id": "OPS-04",
        "name": "OPS-04 | Manager Approval",
        "kind": "power_automate_cloud_flow",
        "deployed": False,
        "depends_on": ["OPS-03"],
    },
    {
        "id": "OPS-05",
        "name": "OPS-05 | Schedule Service Appointment",
        "kind": "power_automate_cloud_flow",
        "deployed": False,
        "depends_on": ["OPS-03"],
    },
    {
        "id": "OPS-06",
        "name": "OPS-06 | SLA Watch",
        "kind": "power_automate_cloud_flow",
        "deployed": False,
        "depends_on": ["OPS-01"],
    },
    {
        "id": "OPS-AGENT-01",
        "name": "OPS-AGENT-01 | Create Case",
        "kind": "copilot_agent_flow",
        "deployed": False,
        "depends_on": [],
    },
    {
        "id": "OPS-AGENT-02",
        "name": "OPS-AGENT-02 | Get Case Status",
        "kind": "copilot_agent_flow",
        "deployed": False,
        "depends_on": ["OPS-AGENT-01"],
    },
    {
        "id": "OPS-AGENT-03",
        "name": "OPS-AGENT-03 | Get My Open Requests",
        "kind": "copilot_agent_flow",
        "deployed": False,
        "depends_on": [],
    },
    {
        "id": "OPS-AGENT-04",
        "name": "OPS-AGENT-04 | Submit Clarification",
        "kind": "copilot_agent_flow",
        "deployed": False,
        "depends_on": ["OPS-AGENT-01"],
    },
)

LOCAL_FLOW_NAMES = {
    "OPS-01": "OPS-01 | Outlook Request Intake",
    "OPS-02": "OPS-02 | Request Classification",
    "OPS-03": "OPS-03 | Assignment and Routing",
    "OPS-04": "OPS-04 | Manager Approval",
    "OPS-05": "OPS-05 | Schedule Service Appointment",
    "OPS-06": "OPS-06 | SLA Watch",
    "OPS-AGENT-01": "OPS-AGENT-01 | Create Case",
    "OPS-AGENT-02": "OPS-AGENT-02 | Get Case Status",
    "OPS-AGENT-03": "OPS-AGENT-03 | Get My Open Requests",
    "OPS-AGENT-04": "OPS-AGENT-04 | Submit Clarification",
}
