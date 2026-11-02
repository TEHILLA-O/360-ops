export type Persona = {
  id: string;
  display_name: string;
  role: string;
  department: string;
  job_title: string;
  identity_source: string;
};

export type CaseSummary = {
  id: string;
  case_number: string;
  title: string;
  status: string;
  approval_state: string;
  priority: string;
  category_id: string | null;
  category_name: string | null;
  requester_department: string;
  owning_department: string | null;
  assigned_team: string | null;
  assigned_agent_id: string | null;
  assigned_agent_name: string | null;
  requester_id: string;
  requester_name: string;
  source_channel: string;
  submitted_at: string;
  due_at: string | null;
  completed_at: string | null;
  sla_state: string;
  sla_elapsed_business_minutes: number | null;
  sla_target_business_minutes: number | null;
  manual_triage: boolean;
  security_flag: boolean;
  blocking_reason: string | null;
  calendar_event_id: string | null;
  version: number;
  classification_confidence: string | null;
  classification_reason: string | null;
  missing_information: string[];
  decision_authorities: string[];
};

export type CaseEvent = {
  id: string;
  case_id: string | null;
  actor_id: string | null;
  action: string;
  occurred_at: string;
  source_system: string;
  previous_state: string | null;
  new_state: string | null;
  reason: string | null;
  correlation_id: string | null;
  integration_ref: string | null;
  metadata: Record<string, unknown>;
  case_number?: string;
  title?: string;
};

export type CaseDetail = CaseSummary & {
  description: string;
  resource_name: string | null;
  justification: string | null;
  preferred_window: string | null;
  resolution_summary: string | null;
  status_sentence: string;
  next_action: string;
  events: CaseEvent[];
  approvals: Array<Record<string, unknown>>;
  assignments: Array<Record<string, unknown>>;
  communications: Array<Record<string, string | null>>;
  documents: Array<Record<string, string | null>>;
  integrations: Array<Record<string, unknown>>;
  escalations: Array<Record<string, string | null>>;
};

export type CommandModel = {
  open_cases: number;
  awaiting_approval: number;
  sla_breaches: number;
  completed_today: number;
  recorded_integration_failures: number;
  lifecycle: Array<{ stage: string; count: number }>;
  service_health: Record<string, string>;
  data_plane: string;
  cloud_flows_deployed: boolean;
};

export type AttentionItem = {
  kind: string;
  case_id: string;
  case_number: string;
  title: string;
  detail: string;
  status: string;
  priority: string;
};
