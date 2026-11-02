import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { formatWhen, words } from "../lib/format";
import { useSession } from "../session";

type ApprovalRow = {
  id: string;
  case_number: string;
  title: string;
  case_status: string;
  state: string;
  approver_name: string | null;
  requested_at: string;
  decided_at: string | null;
  comments: string | null;
  decision_authority: string;
  requested_action: string;
};

const STAGES = ["Submitted", "Manager review", "Decision", "Fulfilment", "Verified"];

export function ApprovalsView() {
  const { personaId } = useSession();
  const query = useQuery({
    queryKey: ["approvals", personaId],
    queryFn: () => api<ApprovalRow[]>("/api/approvals", personaId),
  });
  if (query.isError) return <p className="text-sm text-coral">{query.error instanceof ApiError ? query.error.message : "Approvals unavailable."}</p>;
  return (
    <div className="space-y-4">
      <header>
        <div className="kicker">Approval journey</div>
        <h2 className="text-2xl">Decisions stay attached to the case</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate">
          This screen reads approval rows from the case store. It does not complete a Microsoft Approvals task.
          Rows marked local simulation were written by the demonstration seed or an administrator lab action.
        </p>
      </header>
      <ul className="space-y-3">
        {(query.data || []).map((row) => (
          <li key={row.id} className="border border-ink/10 bg-white p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <Link className="num text-cobalt" to={`/caseflow?case=${row.case_number}`}>{row.case_number}</Link>
              <span className="text-xs uppercase tracking-wide text-slate">{words(row.decision_authority)}</span>
            </div>
            <h3 className="mt-1 text-lg">{row.title}</h3>
            <ol className="mt-4 flex flex-wrap gap-2 text-xs">
              {STAGES.map((stage, index) => (
                <li key={stage} className={`border px-2 py-1 ${stageReached(row, index) ? "border-cobalt text-cobalt" : "border-ink/10 text-slate"}`}>
                  {stage}
                </li>
              ))}
            </ol>
            <dl className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div><dt className="kicker">Approver</dt><dd>{row.approver_name || "Not assigned"}</dd></div>
              <div><dt className="kicker">State</dt><dd>{words(row.state)}</dd></div>
              <div><dt className="kicker">Requested</dt><dd className="num">{formatWhen(row.requested_at)}</dd></div>
              <div><dt className="kicker">Decided</dt><dd className="num">{formatWhen(row.decided_at)}</dd></div>
            </dl>
            <p className="mt-3 text-sm text-slate">{row.requested_action}</p>
            {row.comments && <p className="mt-2 text-sm">Comment: {row.comments}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function stageReached(row: ApprovalRow, index: number) {
  if (index === 0) return true;
  if (index === 1) return true;
  if (index === 2) return row.state === "approved" || row.state === "rejected";
  if (index === 3) return row.case_status === "awaiting_fulfilment" || row.case_status === "resolved" || row.case_status === "closed";
  return row.case_status === "closed";
}
