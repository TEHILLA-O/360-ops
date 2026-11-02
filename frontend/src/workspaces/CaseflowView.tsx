import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { formatWhen, minutes, words } from "../lib/format";
import { useSession } from "../session";
import type { CaseDetail, CaseSummary } from "../types";

const VIEWS = ["Register", "Pipeline", "Priority", "Department", "SLA"] as const;

export function CaseflowView() {
  const { personaId } = useSession();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<(typeof VIEWS)[number]>("Register");
  const [filter, setFilter] = useState("");
  const selected = params.get("case");
  const cases = useQuery({
    queryKey: ["cases", personaId],
    queryFn: () => api<CaseSummary[]>("/api/cases", personaId),
  });
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    let rows = cases.data || [];
    if (needle) rows = rows.filter((item) => `${item.case_number} ${item.title} ${item.requester_name}`.toLowerCase().includes(needle));
    if (view === "Priority") rows = [...rows].sort((a, b) => priorityRank(b.priority) - priorityRank(a.priority));
    if (view === "SLA") rows = [...rows].sort((a, b) => (b.sla_elapsed_business_minutes || 0) - (a.sla_elapsed_business_minutes || 0));
    return rows;
  }, [cases.data, filter, view]);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="flex border border-ink/10 bg-white">
            {VIEWS.map((item) => (
              <button key={item} className={`px-3 py-2 text-sm ${view === item ? "bg-ink text-paper" : ""}`} onClick={() => setView(item)}>
                {item}
              </button>
            ))}
          </div>
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter visible cases"
            className="border border-ink/10 bg-white px-3 py-2 text-sm"
            aria-label="Filter cases"
          />
          <CreateCase />
        </div>
        {view === "Pipeline" ? (
          <Pipeline rows={visible} selected={selected} onSelect={(id) => setParams({ case: id })} />
        ) : view === "Department" ? (
          <Department rows={visible} onSelect={(id) => setParams({ case: id })} />
        ) : (
          <Register rows={visible} selected={selected} onSelect={(id) => setParams({ case: id })} />
        )}
      </section>
      {selected && <Inspector caseId={selected} onClose={() => setParams({})} />}
    </div>
  );
}

function Register({ rows, selected, onSelect }: { rows: CaseSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="overflow-auto border border-ink/10 bg-white">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-paper2 text-xs uppercase tracking-wide text-slate">
          <tr>
            <th className="px-3 py-2 font-medium">Case</th>
            <th className="px-3 py-2 font-medium">Request</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Approval</th>
            <th className="px-3 py-2 font-medium">SLA</th>
            <th className="px-3 py-2 font-medium">Owner</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={item.id} className={selected === item.id ? "bg-paper" : "border-t border-ink/5"}>
              <td className="px-3 py-2">
                <button className="num text-cobalt" onClick={() => onSelect(item.id)}>
                  {item.case_number}
                </button>
              </td>
              <td className="px-3 py-2">
                <div>{item.title}</div>
                <div className="text-xs text-slate">{item.requester_name} · {item.category_name || "Unclassified"}</div>
              </td>
              <td className="px-3 py-2">{words(item.status)}</td>
              <td className="px-3 py-2">{words(item.approval_state)}</td>
              <td className="px-3 py-2"><SlaChip state={item.sla_state} /></td>
              <td className="px-3 py-2 text-xs">{item.assigned_team || "Unassigned"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="px-4 py-8 text-sm text-slate">No visible cases match.</p>}
    </div>
  );
}

function Pipeline({ rows, selected, onSelect }: { rows: CaseSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  const columns = ["new", "awaiting_information", "assigned", "awaiting_approval", "in_progress", "awaiting_fulfilment", "resolved"];
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {columns.map((status) => (
        <section key={status} className="bg-paper2/60 p-2">
          <h3 className="kicker px-1 py-2">{words(status)}</h3>
          <ul className="space-y-2">
            {rows.filter((item) => item.status === status).map((item) => (
              <li key={item.id}>
                <button className={`w-full border bg-white p-3 text-left ${selected === item.id ? "border-cobalt" : "border-ink/10"}`} onClick={() => onSelect(item.id)}>
                  <div className="num text-xs text-cobalt">{item.case_number}</div>
                  <div className="mt-1 text-sm">{item.title}</div>
                  <div className="mt-2"><SlaChip state={item.sla_state} /></div>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Department({ rows, onSelect }: { rows: CaseSummary[]; onSelect: (id: string) => void }) {
  const groups = new Map<string, CaseSummary[]>();
  rows.forEach((item) => {
    const key = item.requester_department;
    groups.set(key, [...(groups.get(key) || []), item]);
  });
  return (
    <div className="space-y-4">
      {[...groups.entries()].map(([department, items]) => (
        <section key={department} className="border border-ink/10 bg-white">
          <h3 className="border-b border-ink/10 px-4 py-2 text-sm">{department} · <span className="num">{items.length}</span></h3>
          <ul>
            {items.map((item) => (
              <li key={item.id}>
                <button className="flex w-full justify-between px-4 py-2 text-left text-sm hover:bg-paper" onClick={() => onSelect(item.id)}>
                  <span><span className="num text-cobalt">{item.case_number}</span> {item.title}</span>
                  <span className="text-slate">{words(item.status)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Inspector({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const { personaId } = useSession();
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: ["case", personaId, caseId],
    queryFn: () => api<CaseDetail>(`/api/cases/${caseId}`, personaId),
  });
  const refresh = () => {
    void client.invalidateQueries();
  };
  if (detail.isError) {
    const message = detail.error instanceof ApiError ? detail.error.message : "Case unavailable.";
    return <aside className="border border-ink/10 bg-white p-4 text-sm">{message}</aside>;
  }
  if (!detail.data) return <aside className="border border-ink/10 bg-white p-4 text-sm text-slate">Opening the case…</aside>;
  const item = detail.data;
  return (
    <aside className="h-fit border border-ink/10 bg-white">
      <div className="flex items-start justify-between border-b border-ink/10 px-4 py-3">
        <div>
          <div className="num text-cobalt">{item.case_number}</div>
          <h2 className="text-lg">{item.title}</h2>
        </div>
        <button onClick={onClose} aria-label="Close case inspector">Close</button>
      </div>
      <div className="space-y-4 px-4 py-4 text-sm">
        <p>{item.status_sentence}</p>
        <p className="text-slate">{item.next_action}</p>
        <dl className="grid grid-cols-2 gap-3 text-xs">
          <Fact label="Requester" value={item.requester_name} />
          <Fact label="Department" value={item.requester_department} />
          <Fact label="Status" value={words(item.status)} />
          <Fact label="Approval" value={words(item.approval_state)} />
          <Fact label="Team" value={item.assigned_team || "Unassigned"} />
          <Fact label="Agent" value={item.assigned_agent_name || "Unclaimed"} />
          <Fact label="SLA" value={`${words(item.sla_state)} · ${minutes(item.sla_elapsed_business_minutes)} / ${minutes(item.sla_target_business_minutes)}`} />
          <Fact label="Channel" value={item.source_channel} />
        </dl>
        {item.decision_authorities.includes("local_simulation") && (
          <p className="border border-amber/40 bg-amber/10 px-3 py-2 text-xs">
            A decision on this case was recorded by the local simulation. It is not a Microsoft Approvals outcome.
          </p>
        )}
        {item.blocking_reason && <p className="text-coral">Blocking: {words(item.blocking_reason)}</p>}
        <p className="whitespace-pre-wrap text-sm">{item.description}</p>
        <h3 className="kicker">Journey</h3>
        <ol className="space-y-2 border-l border-ink/15 pl-3">
          {item.events.map((event) => (
            <li key={event.id}>
              <div className="num text-[11px] text-slate">{formatWhen(event.occurred_at)}</div>
              <div>{words(event.action)}</div>
              {event.reason && <div className="text-xs text-slate">{event.reason}</div>}
            </li>
          ))}
        </ol>
        <Actions item={item} personaId={personaId} onDone={refresh} />
      </div>
    </aside>
  );
}

function Actions({ item, personaId, onDone }: { item: CaseDetail; personaId: string; onDone: () => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const mutation = useMutation({
    mutationFn: async (action: "clarify" | "accept" | "resolve") => {
      if (action === "clarify") {
        return api(`/api/cases/${item.id}/clarification`, personaId, { method: "POST", body: JSON.stringify({ text }) });
      }
      if (action === "accept") return api(`/api/cases/${item.id}/accept`, personaId, { method: "POST" });
      return api(`/api/cases/${item.id}/resolve`, personaId, { method: "POST", body: JSON.stringify({ summary: text }) });
    },
    onSuccess: () => {
      setError("");
      setText("");
      onDone();
    },
    onError: (reason) => setError(reason instanceof ApiError ? reason.message : "The action was rejected."),
  });
  return (
    <div className="space-y-2 border-t border-ink/10 pt-3">
      <label className="block text-xs text-slate">
        Note for clarification or resolution
        <textarea value={text} onChange={(event) => setText(event.target.value)} className="mt-1 w-full border border-ink/10 p-2 text-sm" rows={3} />
      </label>
      <div className="flex flex-wrap gap-2">
        <button className="border border-ink/15 px-3 py-1.5" onClick={() => mutation.mutate("clarify")}>Submit clarification</button>
        <button className="border border-ink/15 px-3 py-1.5" onClick={() => mutation.mutate("accept")}>Accept work</button>
        <button className="border border-ink/15 px-3 py-1.5" onClick={() => mutation.mutate("resolve")}>Record resolution</button>
      </div>
      {error && <p className="text-xs text-coral">{error}</p>}
      <p className="text-[11px] text-slate">The server rejects transitions the role or the case state does not allow. Resolution does not grant access.</p>
    </div>
  );
}

function CreateCase() {
  const { personaId } = useSession();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      api<{ case_number: string; message: string }>("/api/cases", personaId, {
        method: "POST",
        body: JSON.stringify({ title, description }),
      }),
    onSuccess: (result) => {
      setMessage(`${result.case_number}: ${result.message}`);
      setOpen(false);
      void client.invalidateQueries();
    },
    onError: (error) => setMessage(error instanceof ApiError ? error.message : "The case was not created."),
  });
  return (
    <div>
      <button className="bg-cobalt px-3 py-2 text-sm text-white" onClick={() => setOpen(true)}>New request</button>
      {message && <p className="mt-2 text-xs text-slate">{message}</p>}
      {open && (
        <form
          className="mt-3 space-y-2 border border-ink/10 bg-white p-3"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title" className="w-full border border-ink/10 px-2 py-1" required />
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What do you need?" className="w-full border border-ink/10 px-2 py-1" rows={3} required />
          <div className="flex gap-2">
            <button className="bg-ink px-3 py-1 text-sm text-paper" type="submit">Submit</button>
            <button type="button" onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </form>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="kicker">{label}</dt>
      <dd className="mt-1">{value}</dd>
    </div>
  );
}

function SlaChip({ state }: { state: string }) {
  const tone = state === "breached" ? "text-coral" : state === "approaching" || state === "paused" ? "text-amber" : state === "completed" || state === "healthy" ? "text-teal" : "text-slate";
  return <span className={`text-xs uppercase tracking-wide ${tone}`}>{words(state)}</span>;
}

function priorityRank(priority: string) {
  return { low: 0, normal: 1, high: 2, urgent: 3 }[priority] ?? 1;
}
