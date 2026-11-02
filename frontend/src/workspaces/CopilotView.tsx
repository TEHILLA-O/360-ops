import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useSession } from "../session";

type ToolResult = {
  success?: boolean;
  message?: string;
  case_number?: string | null;
  case_id?: string | null;
  status?: string | null;
  next_action?: string | null;
  error_code?: string | null;
  candidates?: Array<{ case_number: string; title: string; status: string }>;
  requests?: Array<{ case_number: string; title: string; status: string }>;
  categories?: Array<{ name: string; approval_policy: string; description: string }>;
};

const PROMPTS = [
  ["Check my finance request", "status", "What's happening with my finance access request?"],
  ["My open requests", "mine", ""],
  ["Explain access approval", "guidance", "access_request"],
  ["Ask the service desk", "escalate", "I still need a person to look at this."],
] as const;

export function CopilotView() {
  const { personaId } = useSession();
  const [text, setText] = useState("What's happening with my finance access request?");
  const [result, setResult] = useState<ToolResult | null>(null);
  const [error, setError] = useState("");

  async function run(kind: string, value: string) {
    setError("");
    try {
      if (kind === "status") {
        setResult(await api<ToolResult>("/api/assistant/status", personaId, { method: "POST", body: JSON.stringify({ text: value }) }));
      } else if (kind === "mine") {
        setResult(await api<ToolResult>("/api/assistant/my-requests", personaId, { method: "POST" }));
      } else if (kind === "guidance") {
        setResult(await api<ToolResult>(`/api/assistant/guidance?category_id=${value}`, personaId, { method: "POST" }));
      } else {
        setResult(await api<ToolResult>("/api/assistant/escalate", personaId, { method: "POST", body: JSON.stringify({ question: value }) }));
      }
    } catch (reason) {
      setResult(null);
      setError(reason instanceof ApiError ? reason.message : "The tool did not respond.");
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="border border-ink/10 bg-white p-4">
        <div className="kicker">OpsPilot Assistant</div>
        <h2 className="mt-2 text-xl">Tool contract</h2>
        <p className="mt-3 text-sm text-slate">
          Copilot Studio is not connected. These buttons call the same structured tools specified for OPS-AGENT flows.
          The reply is the API payload, not a generated chat.
        </p>
        <ul className="mt-4 space-y-2">
          {PROMPTS.map(([label, kind, value]) => (
            <li key={label}>
              <button className="w-full border border-ink/10 px-3 py-2 text-left text-sm hover:bg-paper" onClick={() => run(kind, kind === "status" ? text : value)}>
                {label}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="border border-ink/10 bg-white p-5">
        <label className="block text-sm">
          Status question
          <textarea value={text} onChange={(event) => setText(event.target.value)} className="mt-2 w-full border border-ink/10 p-3" rows={3} />
        </label>
        <button className="mt-3 bg-cobalt px-3 py-2 text-sm text-white" onClick={() => run("status", text)}>Ask the case store</button>
        {error && <p className="mt-4 text-sm text-coral">{error}</p>}
        {result && (
          <article className="mt-6 border-t border-ink/10 pt-4">
            <p className="text-lg">{result.message}</p>
            {result.case_number && (
              <p className="mt-3 text-sm">
                Case <Link className="num text-cobalt" to={`/caseflow?case=${result.case_id}`}>{result.case_number}</Link>
                {result.status ? ` · ${result.status.replaceAll("_", " ")}` : ""}
              </p>
            )}
            {result.next_action && <p className="mt-2 text-sm text-slate">{result.next_action}</p>}
            {result.error_code && <p className="mt-2 text-xs uppercase tracking-wide text-slate">Tool code {result.error_code}</p>}
            <ul className="mt-3 space-y-1 text-sm">
              {(result.candidates || result.requests || []).map((item) => (
                <li key={item.case_number} className="num">{item.case_number} · {item.title}</li>
              ))}
              {(result.categories || []).map((item) => (
                <li key={item.name}>{item.name}: {item.approval_policy.replaceAll("_", " ")}. {item.description}</li>
              ))}
            </ul>
          </article>
        )}
      </section>
    </div>
  );
}
