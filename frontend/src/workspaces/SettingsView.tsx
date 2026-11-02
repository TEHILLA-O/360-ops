import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useSession } from "../session";

type Category = {
  id: string;
  name: string;
  description: string;
  required_fields: string[];
  approval_policy: string;
  sla_resolution_business_minutes: Record<string, number>;
  resolution_requirements: string;
};

export function SettingsView() {
  const { personaId } = useSession();
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/api/categories", personaId) });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: () => api<{ dependencies: Array<{ name: string; status: string; note: string }> }>("/api/capabilities", personaId) });
  const transitions = useQuery({ queryKey: ["transitions"], queryFn: () => api<Record<string, string[]>>("/api/transitions", personaId) });
  return (
    <div className="space-y-6">
      <header>
        <div className="kicker">Configuration</div>
        <h2 className="text-2xl">Policy lives in the service, not in the page</h2>
      </header>
      <section className="grid gap-3 md:grid-cols-2">
        {(capabilities.data?.dependencies || []).map((item) => (
          <article key={item.name} className="border border-ink/10 bg-white p-4">
            <div className="flex justify-between gap-3">
              <h3 className="text-sm">{item.name}</h3>
              <span className="text-xs uppercase tracking-wide text-slate">{item.status.replaceAll("_", " ")}</span>
            </div>
            <p className="mt-2 text-sm text-slate">{item.note}</p>
          </article>
        ))}
      </section>
      <section className="space-y-3">
        {(categories.data || []).map((category) => (
          <article key={category.id} className="border border-ink/10 bg-white p-4">
            <h3>{category.name}</h3>
            <p className="mt-1 text-sm text-slate">{category.description}</p>
            <p className="mt-2 text-sm">Approval: {category.approval_policy.replaceAll("_", " ")}. Required: {category.required_fields.join(", ")}.</p>
            <p className="mt-1 text-sm">Resolution: {category.resolution_requirements}</p>
            <p className="num mt-2 text-xs text-slate">
              SLA minutes — {Object.entries(category.sla_resolution_business_minutes).map(([priority, minutes]) => `${priority} ${minutes}`).join(" · ")}
            </p>
          </article>
        ))}
      </section>
      <section className="border border-ink/10 bg-white p-4">
        <h3 className="kicker">Allowed status moves</h3>
        <ul className="mt-3 space-y-1 text-sm">
          {Object.entries(transitions.data || {}).map(([status, targets]) => (
            <li key={status}><span className="font-medium">{status.replaceAll("_", " ")}</span> → {targets.join(", ").replaceAll("_", " ") || "none"}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
