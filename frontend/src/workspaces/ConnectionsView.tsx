import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api";
import { useSession } from "../session";

type Connection = { id: string; name: string; state: string; detail: string };

const SCOPES = ["User.Read", "Mail.ReadBasic", "Files.Read", "Calendars.ReadWrite"];

export function ConnectionsView() {
  const { personaId } = useSession();
  const connections = useQuery({
    queryKey: ["connections", personaId],
    queryFn: () => api<Connection[]>("/api/connections", personaId),
  });
  const [probe, setProbe] = useState("");
  async function runProbe() {
    try {
      const result = await api<Record<string, unknown>>("/api/connections/graph/probe", personaId, { method: "POST" });
      setProbe(JSON.stringify(result, null, 2));
    } catch (error) {
      setProbe(error instanceof ApiError ? `${error.body.error_code || "error"}: ${error.message}` : "Probe failed.");
    }
  }
  return (
    <div className="space-y-4">
      <header>
        <div className="kicker">Microsoft connections</div>
        <h2 className="text-2xl">What this environment can actually call</h2>
      </header>
      <ul className="grid gap-3 md:grid-cols-2">
        {(connections.data || []).map((item) => (
          <li key={item.id} className="border border-ink/10 bg-white p-4">
            <div className="flex items-baseline justify-between">
              <h3>{item.name}</h3>
              <span className="text-xs uppercase tracking-wide text-slate">{item.state.replaceAll("_", " ")}</span>
            </div>
            <p className="mt-2 text-sm text-slate">{item.detail}</p>
          </li>
        ))}
      </ul>
      <section className="border border-ink/10 bg-white p-4">
        <h3 className="text-sm">Delegated Graph scopes requested by the service</h3>
        <ul className="mt-2 flex flex-wrap gap-2">
          {SCOPES.map((scope) => (
            <li key={scope} className="num border border-ink/10 px-2 py-1 text-xs">{scope}</li>
          ))}
        </ul>
        <p className="mt-3 text-sm text-slate">Administrator consent is required before the first sign-in. The client secret stays on the server. This page never shows tokens.</p>
        <button className="mt-3 border border-ink/15 px-3 py-2 text-sm" onClick={() => void runProbe()}>Probe Graph profile</button>
        {probe && <pre className="mt-3 overflow-auto bg-paper p-3 text-xs">{probe}</pre>}
      </section>
    </div>
  );
}
