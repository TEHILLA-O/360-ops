import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { formatWhen, words } from "../lib/format";
import { useSession } from "../session";
import type { AttentionItem, CaseEvent, CommandModel } from "../types";

const STAGE_LABEL: Record<string, string> = {
  new: "New",
  classification: "Classification",
  assignment: "Assignment",
  approval: "Approval",
  in_progress: "In progress",
  fulfilment: "Fulfilment",
  resolution: "Resolution",
};

export function CommandView() {
  const { personaId } = useSession();
  const navigate = useNavigate();
  const command = useQuery({
    queryKey: ["command", personaId],
    queryFn: () => api<CommandModel>("/api/command", personaId),
  });
  const attention = useQuery({
    queryKey: ["attention", personaId],
    queryFn: () => api<AttentionItem[]>("/api/attention", personaId),
  });
  const timeline = useQuery({
    queryKey: ["timeline", personaId],
    queryFn: () => api<CaseEvent[]>("/api/timeline?limit=12", personaId),
  });
  if (command.isError) return <ErrorState error={command.error} />;
  if (!command.data) return <p className="text-sm text-slate">Reading the local case store…</p>;
  const model = command.data;
  const readings = [
    ["Open cases", model.open_cases],
    ["Awaiting approval", model.awaiting_approval],
    ["SLA breaches", model.sla_breaches],
    ["Completed today", model.completed_today],
    ["Recorded failures", model.recorded_integration_failures],
    ["Cloud flows", model.cloud_flows_deployed ? "Deployed" : "Not deployed"],
  ];
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 border border-ink/10 bg-white md:grid-cols-6">
        {readings.map(([label, value]) => (
          <div key={String(label)} className="border-ink/10 px-4 py-3 md:border-r md:last:border-r-0">
            <div className="kicker">{label}</div>
            <div className="num mt-2 text-2xl">{value}</div>
          </div>
        ))}
      </section>
      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.8fr)]">
        <div className="border border-ink/10 bg-white p-5">
          <div className="kicker">Service operations lifecycle</div>
          <h2 className="mt-1 text-lg">Cases visible to this persona</h2>
          <Lifecycle stages={model.lifecycle} onPick={() => navigate("/caseflow")} />
          <p className="mt-3 text-xs text-slate">Counts are grouped from stored statuses. They are not estimated.</p>
        </div>
        <aside className="border border-ink/10 bg-white">
          <div className="border-b border-ink/10 px-4 py-3">
            <div className="kicker">Attention</div>
          </div>
          <ul>
            {(attention.data || []).slice(0, 8).map((item) => (
              <li key={`${item.kind}-${item.case_id}`} className="border-b border-ink/5">
                <button className="block w-full px-4 py-3 text-left hover:bg-paper" onClick={() => navigate(`/caseflow?case=${item.case_id}`)}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="num text-xs text-cobalt">{item.case_number}</span>
                    <span className="text-[11px] uppercase tracking-wide text-slate">{words(item.kind)}</span>
                  </div>
                  <div className="mt-1 text-sm">{item.title}</div>
                  <div className="mt-1 text-xs text-slate">{item.detail}</div>
                </button>
              </li>
            ))}
            {attention.data && attention.data.length === 0 && <li className="px-4 py-6 text-sm text-slate">Nothing in this persona's queue needs attention.</li>}
          </ul>
        </aside>
      </section>
      <section className="border border-ink/10 bg-white">
        <div className="border-b border-ink/10 px-4 py-3">
          <div className="kicker">Operational timeline</div>
        </div>
        <ol>
          {(timeline.data || []).map((event) => (
            <li key={event.id}>
              <button
                className="grid w-full grid-cols-[140px_1fr_auto] gap-4 px-4 py-3 text-left hover:bg-paper"
                onClick={() => event.case_id && navigate(`/caseflow?case=${event.case_id}`)}
              >
                <span className="num text-xs text-slate">{formatWhen(event.occurred_at)}</span>
                <span>
                  <span className="text-sm">{words(event.action)}</span>
                  <span className="mt-0.5 block text-xs text-slate">{event.title || event.reason || event.source_system}</span>
                </span>
                <span className="num text-xs text-cobalt">{event.case_number}</span>
              </button>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function Lifecycle({ stages, onPick }: { stages: CommandModel["lifecycle"]; onPick: () => void }) {
  return (
    <div className="mt-6 overflow-x-auto">
      <div className="flex min-w-[760px] items-start">
        {stages.map((stage, index) => (
          <button key={stage.stage} className="flex flex-1 flex-col items-center" onClick={onPick}>
            <div className="flex w-full items-center">
              <span className={`h-px flex-1 ${index === 0 ? "bg-transparent" : "bg-ink/15"}`} />
              <span className="grid h-14 w-14 place-items-center rounded-full border border-cobalt/30 bg-paper">
                <span className="num text-lg">{stage.count}</span>
              </span>
              <span className={`h-px flex-1 ${index === stages.length - 1 ? "bg-transparent" : "bg-ink/15"}`} />
            </div>
            <span className="mt-2 text-center text-xs text-slate">{STAGE_LABEL[stage.stage] || stage.stage}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : "The case service did not respond.";
  return <p className="text-sm text-coral">{message}</p>;
}
