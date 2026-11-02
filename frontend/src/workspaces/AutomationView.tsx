import { Background, Controls, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { formatWhen } from "../lib/format";
import { useSession } from "../session";

type FlowCard = {
  id: string;
  name: string;
  deployed: boolean;
  depends_on: string[];
  observed_local_runs: number;
  observed_local_failures: number;
  observed_cloud_runs: number;
  last_local_run_at: string | null;
  last_local_outcome: string | null;
};

const POSITIONS: Record<string, { x: number; y: number }> = {
  "OPS-01": { x: 0, y: 80 },
  "OPS-02": { x: 240, y: 80 },
  "OPS-03": { x: 480, y: 80 },
  "OPS-04": { x: 720, y: 0 },
  "OPS-05": { x: 720, y: 160 },
  "OPS-06": { x: 240, y: 240 },
  "OPS-AGENT-01": { x: 0, y: 360 },
  "OPS-AGENT-02": { x: 240, y: 360 },
  "OPS-AGENT-03": { x: 480, y: 360 },
  "OPS-AGENT-04": { x: 720, y: 360 },
};

export function AutomationView() {
  const { personaId } = useSession();
  const board = useQuery({
    queryKey: ["workflows", personaId],
    queryFn: () => api<{ flows: FlowCard[]; note: string }>("/api/workflows", personaId),
  });
  const flows = board.data?.flows || [];
  const nodes = flows.map((flow) => ({
    id: flow.id,
    position: POSITIONS[flow.id] || { x: 0, y: 0 },
    data: { label: `${flow.id}\n${flow.observed_cloud_runs} cloud · ${flow.observed_local_runs} local` },
    style: {
      width: 190,
      fontSize: 12,
      border: "1px solid rgba(28,30,34,0.15)",
      background: flow.observed_local_failures ? "#f8ecea" : "#fff",
      whiteSpace: "pre-line" as const,
    },
  }));
  const edges = flows.flatMap((flow) => flow.depends_on.map((source) => ({ id: `${source}-${flow.id}`, source, target: flow.id })));
  return (
    <div className="space-y-4">
      <header>
        <div className="kicker">Automation observatory</div>
        <h2 className="text-2xl">Specified flows, measured runs</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate">{board.data?.note}</p>
      </header>
      <div className="h-[520px] border border-ink/10 bg-white">
        <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <div className="overflow-auto border border-ink/10 bg-white">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate">
            <tr>
              <th className="px-3 py-2">Flow</th>
              <th className="px-3 py-2">Deployed</th>
              <th className="px-3 py-2">Cloud runs</th>
              <th className="px-3 py-2">Local runs</th>
              <th className="px-3 py-2">Local failures</th>
              <th className="px-3 py-2">Last local run</th>
            </tr>
          </thead>
          <tbody>
            {flows.map((flow) => (
              <tr key={flow.id} className="border-t border-ink/5">
                <td className="px-3 py-2">{flow.name}</td>
                <td className="px-3 py-2">{flow.deployed ? "Yes" : "No"}</td>
                <td className="num px-3 py-2">{flow.observed_cloud_runs}</td>
                <td className="num px-3 py-2">{flow.observed_local_runs}</td>
                <td className="num px-3 py-2">{flow.observed_local_failures}</td>
                <td className="px-3 py-2">{flow.last_local_run_at ? `${formatWhen(flow.last_local_run_at)} · ${flow.last_local_outcome}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
