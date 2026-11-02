"""Append-friendly SQLite store.

Audit rows are inserted and never updated. Case rows carry a version so a
stale write fails instead of overwriting a newer decision.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS requesters (
  id TEXT PRIMARY KEY,
  upn TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  department TEXT NOT NULL,
  job_title TEXT NOT NULL,
  role TEXT NOT NULL,
  manager_id TEXT,
  teams_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY,
  case_number TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  category_id TEXT,
  requester_id TEXT NOT NULL REFERENCES requesters(id),
  requester_department TEXT NOT NULL,
  owning_department TEXT,
  assigned_team TEXT,
  assigned_agent_id TEXT,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_state TEXT NOT NULL,
  source_channel TEXT NOT NULL,
  source_message_id TEXT,
  source_mailbox TEXT,
  dedup_key TEXT UNIQUE,
  submitted_at TEXT NOT NULL,
  due_at TEXT,
  completed_at TEXT,
  resolution_summary TEXT,
  version INTEGER NOT NULL,
  manual_triage INTEGER NOT NULL DEFAULT 0,
  classification_confidence TEXT,
  classification_reason TEXT,
  missing_information_json TEXT NOT NULL DEFAULT '[]',
  correlation_id TEXT,
  resource_name TEXT,
  justification TEXT,
  preferred_window TEXT,
  security_flag INTEGER NOT NULL DEFAULT 0,
  calendar_event_id TEXT,
  blocking_reason TEXT
);
CREATE TABLE IF NOT EXISTS assignments (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES requests(id),
  team TEXT,
  agent_id TEXT,
  rule_id TEXT,
  rule_version TEXT,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES requests(id),
  approver_id TEXT,
  state TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  comments TEXT,
  decision_authority TEXT NOT NULL,
  recorded_by TEXT NOT NULL,
  workflow_run_ref TEXT,
  correlation_id TEXT,
  requested_action TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_events (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  source_system TEXT NOT NULL,
  previous_state TEXT,
  new_state TEXT,
  reason TEXT,
  correlation_id TEXT,
  integration_ref TEXT,
  safe_metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  case_id TEXT,
  actor_id TEXT,
  action TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  source_system TEXT NOT NULL,
  previous_state TEXT,
  new_state TEXT,
  reason TEXT,
  correlation_id TEXT,
  integration_ref TEXT,
  safe_metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS communications (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  direction TEXT NOT NULL,
  template TEXT NOT NULL,
  safe_body TEXT NOT NULL,
  delivery_status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  recipient_ref TEXT
);
CREATE TABLE IF NOT EXISTS document_references (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  source TEXT NOT NULL,
  owner_id TEXT,
  uploaded_at TEXT NOT NULL,
  version_label TEXT NOT NULL,
  access_state TEXT NOT NULL,
  review_state TEXT NOT NULL,
  sharepoint_item_id TEXT
);
CREATE TABLE IF NOT EXISTS sla_snapshots (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  state TEXT NOT NULL,
  evaluated_at TEXT NOT NULL,
  elapsed_business_minutes INTEGER NOT NULL,
  target_business_minutes INTEGER,
  due_at TEXT,
  policy_version TEXT NOT NULL,
  kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS escalations (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  dedup_key TEXT UNIQUE NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  notified_status TEXT NOT NULL,
  threshold TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_runs (
  id TEXT PRIMARY KEY,
  flow_name TEXT NOT NULL,
  flow_id TEXT NOT NULL,
  source TEXT NOT NULL,
  operation TEXT NOT NULL,
  run_ref TEXT,
  correlation_id TEXT,
  case_id TEXT,
  trigger_name TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  outcome TEXT NOT NULL,
  error_category TEXT,
  error_code TEXT,
  safe_message TEXT,
  attempt INTEGER NOT NULL,
  predecessor_id TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  case_id TEXT,
  channel TEXT NOT NULL,
  template TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  safe_summary TEXT NOT NULL,
  recipient_ref TEXT
);
CREATE TABLE IF NOT EXISTS idempotency (
  key TEXT PRIMARY KEY,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  status_code INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sequences (
  name TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()

    def close(self) -> None:
        self.conn.close()

    def init(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT OR IGNORE INTO sequences(name, value) VALUES ('case', 2999)"
            )
            self.conn.commit()

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def count_requests(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM requests").fetchone()
        return int(row["n"])

    def allocate_case_number(self, conn: sqlite3.Connection) -> str:
        row = conn.execute("SELECT value FROM sequences WHERE name = 'case'").fetchone()
        value = int(row["value"]) + 1
        conn.execute("UPDATE sequences SET value = ? WHERE name = 'case'", (value,))
        return f"NS-{value}"

    def upsert_requester(self, conn: sqlite3.Connection, person: dict) -> None:
        conn.execute(
            """
            INSERT INTO requesters (id, upn, display_name, department, job_title, role, manager_id, teams_json)
            VALUES (:id, :upn, :display_name, :department, :job_title, :role, :manager_id, :teams_json)
            ON CONFLICT(id) DO UPDATE SET
              display_name = excluded.display_name,
              department = excluded.department,
              job_title = excluded.job_title,
              role = excluded.role,
              manager_id = excluded.manager_id,
              teams_json = excluded.teams_json
            """,
            {
                **person,
                "teams_json": json.dumps(person.get("teams") or []),
                "manager_id": person.get("manager_id"),
            },
        )

    def list_requesters(self) -> list[dict]:
        return [self._requester(row) for row in self.conn.execute("SELECT * FROM requesters ORDER BY display_name")]

    def get_requester(self, requester_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM requesters WHERE id = ?", (requester_id,)).fetchone()
        return self._requester(row) if row else None

    def get_requester_by_upn(self, upn: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM requesters WHERE lower(upn) = lower(?)", (upn,)).fetchone()
        return self._requester(row) if row else None

    def insert_request(self, conn: sqlite3.Connection, case: dict) -> None:
        conn.execute(
            """
            INSERT INTO requests (
              id, case_number, title, description, category_id, requester_id, requester_department,
              owning_department, assigned_team, assigned_agent_id, priority, status, approval_state,
              source_channel, source_message_id, source_mailbox, dedup_key, submitted_at, due_at,
              completed_at, resolution_summary, version, manual_triage, classification_confidence,
              classification_reason, missing_information_json, correlation_id, resource_name,
              justification, preferred_window, security_flag, calendar_event_id, blocking_reason
            ) VALUES (
              :id, :case_number, :title, :description, :category_id, :requester_id, :requester_department,
              :owning_department, :assigned_team, :assigned_agent_id, :priority, :status, :approval_state,
              :source_channel, :source_message_id, :source_mailbox, :dedup_key, :submitted_at, :due_at,
              :completed_at, :resolution_summary, :version, :manual_triage, :classification_confidence,
              :classification_reason, :missing_information_json, :correlation_id, :resource_name,
              :justification, :preferred_window, :security_flag, :calendar_event_id, :blocking_reason
            )
            """,
            case,
        )

    def update_request(self, conn: sqlite3.Connection, case_id: str, version: int, fields: dict) -> int:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [version + 1, case_id, version]
        cursor = conn.execute(
            f"UPDATE requests SET {assignments}, version = ? WHERE id = ? AND version = ?",
            values,
        )
        return cursor.rowcount

    def get_request(self, case_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM requests WHERE id = ?", (case_id,)).fetchone()
        return dict(row) if row else None

    def get_request_by_number(self, case_number: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM requests WHERE case_number = ?",
            (case_number,),
        ).fetchone()
        return dict(row) if row else None

    def get_request_by_dedup(self, dedup_key: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM requests WHERE dedup_key = ?", (dedup_key,)).fetchone()
        return dict(row) if row else None

    def list_requests(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM requests ORDER BY submitted_at DESC")]

    def insert_child(self, conn: sqlite3.Connection, table: str, row: dict) -> None:
        columns = ", ".join(row.keys())
        placeholders = ", ".join(f":{key}" for key in row)
        conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", row)

    def list_where(self, table: str, column: str, value: str) -> list[dict]:
        return [
            dict(row)
            for row in self.conn.execute(
                f"SELECT * FROM {table} WHERE {column} = ? ORDER BY rowid",
                (value,),
            )
        ]

    def list_all(self, table: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]

    def get_row(self, table: str, row_id: str) -> dict | None:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row else None

    def update_approval(self, conn: sqlite3.Connection, approval_id: str, fields: dict) -> int:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        cursor = conn.execute(
            f"UPDATE approvals SET {assignments} WHERE id = ? AND state = 'pending'",
            [*fields.values(), approval_id],
        )
        return cursor.rowcount

    def insert_idempotency(self, conn: sqlite3.Connection, key: str, request_hash: str, status: int, body: dict) -> None:
        conn.execute(
            """
            INSERT INTO idempotency (key, request_hash, response_json, status_code, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, request_hash, json.dumps(body), status, _now()),
        )

    def get_idempotency(self, key: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM idempotency WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _requester(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["teams"] = json.loads(data.pop("teams_json") or "[]")
        return data
