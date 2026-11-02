import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { formatWhen } from "../lib/format";
import { useSession } from "../session";

type DocumentRow = {
  id: string;
  case_number: string;
  filename: string;
  doc_type: string;
  source: string;
  uploaded_at: string;
  version_label: string;
  access_state: string;
  review_state: string;
  sharepoint_item_id: string | null;
  sharepoint_connected: boolean;
};

export function DocumentsView() {
  const { personaId } = useSession();
  const documents = useQuery({
    queryKey: ["documents", personaId],
    queryFn: () => api<DocumentRow[]>("/api/documents", personaId),
  });
  return (
    <div className="space-y-4">
      <header>
        <div className="kicker">Case documents</div>
        <h2 className="text-2xl">References, not copies</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate">
          SharePoint is not connected. These rows are metadata. OpsPilot has not downloaded file bytes and cannot bypass SharePoint permissions.
        </p>
      </header>
      <div className="overflow-auto border border-ink/10 bg-white">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate">
            <tr>
              <th className="px-3 py-2">File</th>
              <th className="px-3 py-2">Case</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Recorded</th>
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2">Access</th>
              <th className="px-3 py-2">Review</th>
            </tr>
          </thead>
          <tbody>
            {(documents.data || []).map((row) => (
              <tr key={row.id} className="border-t border-ink/5">
                <td className="px-3 py-2">{row.filename}</td>
                <td className="num px-3 py-2">{row.case_number}</td>
                <td className="px-3 py-2">{row.source}</td>
                <td className="num px-3 py-2">{formatWhen(row.uploaded_at)}</td>
                <td className="num px-3 py-2">{row.version_label}</td>
                <td className="px-3 py-2">{row.access_state.replaceAll("_", " ")}</td>
                <td className="px-3 py-2">{row.review_state.replaceAll("_", " ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
