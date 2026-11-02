import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../session";
import type { CaseSummary, Persona } from "../types";
import { words } from "../lib/format";

const LINKS = [
  ["/", "Command"],
  ["/caseflow", "Caseflow"],
  ["/approvals", "Approvals"],
  ["/copilot", "Copilot"],
  ["/automation", "Automation"],
  ["/connections", "Connections"],
  ["/documents", "Documents"],
  ["/intelligence", "Intelligence"],
  ["/audit", "Audit"],
  ["/settings", "Settings"],
] as const;

export function Chrome({ children }: { children: ReactNode }) {
  const { personaId, setPersonaId } = useSession();
  const navigate = useNavigate();
  const [palette, setPalette] = useState(false);
  const [query, setQuery] = useState("");
  const personas = useQuery({
    queryKey: ["personas"],
    queryFn: () => api<{ personas: Persona[]; identity_source: string }>("/api/personas", personaId),
  });
  const cases = useQuery({
    queryKey: ["cases", personaId],
    queryFn: () => api<CaseSummary[]>("/api/cases", personaId),
  });
  const current = personas.data?.personas.find((person) => person.id === personaId);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette(true);
      }
      if (event.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const jumps = LINKS.filter(([, label]) => label.toLowerCase().includes(needle)).map(([path, label]) => ({
      id: path,
      label,
      hint: "Workspace",
      go: () => navigate(path),
    }));
    const found = (cases.data || [])
      .filter((item) => `${item.case_number} ${item.title}`.toLowerCase().includes(needle))
      .slice(0, 6)
      .map((item) => ({
        id: item.id,
        label: `${item.case_number}  ${item.title}`,
        hint: words(item.status),
        go: () => navigate(`/caseflow?case=${item.id}`),
      }));
    return [...jumps, ...found].slice(0, 10);
  }, [cases.data, navigate, query]);

  return (
    <div className="min-h-screen bg-paper text-ink">
      <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="bg-graphite-950 text-paper">
        <div className="flex items-center gap-6 px-5 py-3">
          <div className="flex items-center gap-3">
            <Mark />
            <div>
              <div className="text-sm font-medium tracking-wide">OpsPilot 365</div>
              <div className="text-[11px] text-paper/60">Northstar Operations Group</div>
            </div>
          </div>
          <div className="hidden text-[11px] uppercase tracking-[0.16em] text-paper/50 lg:block">Local synthetic · Cloud flows not deployed</div>
          <button
            className="ml-auto flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-sm text-paper/80"
            onClick={() => setPalette(true)}
          >
            <Search size={14} />
            <span>Search</span>
            <span className="num text-[11px] text-paper/40">Ctrl K</span>
          </button>
          <label className="text-xs text-paper/70">
            <span className="sr-only">Local persona</span>
            <select
              className="bg-transparent text-sm text-paper"
              value={personaId}
              onChange={(event) => setPersonaId(event.target.value)}
              aria-label="Local synthetic persona"
            >
              {(personas.data?.personas || []).map((person) => (
                <option key={person.id} value={person.id} className="text-ink">
                  {person.display_name} · {words(person.role)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <nav className="flex flex-wrap gap-1 px-3 pb-2" aria-label="Workspaces">
          {LINKS.map(([path, label]) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                `whitespace-nowrap px-3 py-2 text-sm ${isActive ? "text-paper underline decoration-cobalt decoration-2 underline-offset-8" : "text-paper/60"}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <div className="border-b border-ink/10 bg-paper2/70 px-5 py-2 text-xs text-slate">
        Signed in locally as {current ? `${current.display_name}, ${current.job_title}` : personaId}. This is not a Microsoft Entra session.
        Case records come from the local store. Microsoft Graph, Power Automate and Copilot Studio are not connected.
      </div>
      <main id="content" className="px-5 py-6">
        {children}
      </main>
      {palette && (
        <div className="fixed inset-0 z-40 bg-graphite-950/50" onClick={() => setPalette(false)}>
          <div
            role="dialog"
            aria-label="Command palette"
            className="mx-auto mt-24 w-[min(640px,92vw)] bg-paper shadow-lift"
            onClick={(event) => event.stopPropagation()}
          >
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a case, workspace, or record"
              className="w-full border-b border-ink/10 bg-transparent px-4 py-3 text-base outline-none"
            />
            <ul className="max-h-80 overflow-auto py-2">
              {results.map((item) => (
                <li key={item.id}>
                  <button
                    className="flex w-full items-baseline justify-between px-4 py-2 text-left hover:bg-paper2"
                    onClick={() => {
                      item.go();
                      setPalette(false);
                      setQuery("");
                    }}
                  >
                    <span>{item.label}</span>
                    <span className="text-xs text-slate">{item.hint}</span>
                  </button>
                </li>
              ))}
              {results.length === 0 && <li className="px-4 py-6 text-sm text-slate">Nothing in the local store matches.</li>}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function Mark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="2" y="8" width="10" height="10" fill="#2a4f86" />
      <rect x="10" y="4" width="10" height="10" fill="#1c6b5a" />
      <rect x="16" y="14" width="10" height="10" fill="#8a5a10" />
    </svg>
  );
}
