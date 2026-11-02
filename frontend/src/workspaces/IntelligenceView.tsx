import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api";
import { minutes, percent } from "../lib/format";
import { useSession } from "../session";

type Analytics = {
  freshness: string;
  definitions: Record<string, string>;
  metrics: Record<string, number | null>;
  by_category: Array<{ label: string; count: number }>;
  by_department: Array<{ label: string; count: number }>;
  ageing_open_cases_calendar_days: Record<string, number>;
  failure_causes: Array<{ error_code: string; count: number }>;
  bottleneck: { statement: string } | null;
  power_automate_runs_in_window: number;
  notes: string[];
};

export function IntelligenceView() {
  const { personaId } = useSession();
  const report = useQuery({
    queryKey: ["analytics", personaId],
    queryFn: () => api<Analytics>("/api/analytics", personaId),
  });
  if (report.isError) {
    return <p className="max-w-xl text-sm text-slate">{report.error instanceof ApiError ? report.error.message : "Analytics unavailable."} Operational measures are limited to operations, audit and management roles.</p>;
  }
  if (!report.data) return <p className="text-sm text-slate">Computing measures from stored cases…</p>;
  const data = report.data;
  const metrics = [
    ["Received", data.metrics.received],
    ["Completed", data.metrics.completed],
    ["First response", minutes(data.metrics.avg_first_response_business_minutes)],
    ["Resolution", minutes(data.metrics.avg_resolution_business_minutes)],
    ["SLA compliance", percent(data.metrics.sla_compliance_rate)],
    ["Approval turnaround", minutes(data.metrics.avg_approval_turnaround_business_minutes)],
    ["Integration success", percent(data.metrics.recorded_integration_success_rate)],
    ["Escalation rate", percent(data.metrics.escalation_rate)],
    ["Reopened", data.metrics.reopened],
    ["Integration failure", percent(data.metrics.recorded_integration_failure_rate)],
  ];
  return (
    <div className="space-y-5">
      <header>
        <div className="kicker">Operational intelligence</div>
        <h2 className="text-2xl">Measures from the case store</h2>
        <p className="mt-2 text-sm text-slate">Freshness: {data.freshness}. Power Automate runs in the window: {data.power_automate_runs_in_window}.</p>
      </header>
      {data.bottleneck && <p className="border border-ink/10 bg-white px-4 py-3 text-sm">{data.bottleneck.statement}</p>}
      <section className="grid grid-cols-2 border border-ink/10 bg-white md:grid-cols-5">
        {metrics.map(([label, value]) => (
          <div key={String(label)} className="border-b border-r border-ink/10 px-3 py-3">
            <div className="kicker">{label}</div>
            <div className="num mt-1 text-xl">{value ?? "—"}</div>
          </div>
        ))}
      </section>
      <div className="grid gap-4 lg:grid-cols-2">
        <Chart title="Requests by category" rows={data.by_category} />
        <Chart title="Requests by department" rows={data.by_department} />
      </div>
      <section className="border border-ink/10 bg-white p-4 text-sm">
        <h3 className="kicker">Definitions</h3>
        <ul className="mt-3 space-y-2">
          {Object.entries(data.definitions).map(([key, text]) => (
            <li key={key}><span className="font-medium">{key.replaceAll("_", " ")}.</span> {text}</li>
          ))}
        </ul>
        <ul className="mt-4 space-y-1 text-slate">
          {data.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      </section>
    </div>
  );
}

function Chart({ title, rows }: { title: string; rows: Array<{ label: string; count: number }> }) {
  return (
    <section className="border border-ink/10 bg-white p-3">
      <h3 className="px-2 text-sm">{title}</h3>
      <ReactECharts
        style={{ height: 260 }}
        option={{
          grid: { left: 120, right: 16, top: 16, bottom: 24 },
          xAxis: { type: "value", axisLabel: { fontFamily: "IBM Plex Mono" } },
          yAxis: { type: "category", data: rows.map((row) => row.label || "Unspecified"), axisLabel: { fontFamily: "IBM Plex Sans" } },
          series: [{ type: "bar", data: rows.map((row) => row.count), itemStyle: { color: "#2a4f86" } }],
          tooltip: { trigger: "axis" },
        }}
      />
    </section>
  );
}
