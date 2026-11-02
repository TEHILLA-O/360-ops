import { Route, Routes } from "react-router-dom";
import { SessionProvider } from "./session";
import { Chrome } from "./shell/Chrome";
import { ApprovalsView } from "./workspaces/ApprovalsView";
import { AuditView } from "./workspaces/AuditView";
import { AutomationView } from "./workspaces/AutomationView";
import { CaseflowView } from "./workspaces/CaseflowView";
import { CommandView } from "./workspaces/CommandView";
import { ConnectionsView } from "./workspaces/ConnectionsView";
import { CopilotView } from "./workspaces/CopilotView";
import { DocumentsView } from "./workspaces/DocumentsView";
import { IntelligenceView } from "./workspaces/IntelligenceView";
import { SettingsView } from "./workspaces/SettingsView";

export function App() {
  return (
    <SessionProvider>
      <Chrome>
        <Routes>
          <Route path="/" element={<CommandView />} />
          <Route path="/caseflow" element={<CaseflowView />} />
          <Route path="/approvals" element={<ApprovalsView />} />
          <Route path="/copilot" element={<CopilotView />} />
          <Route path="/automation" element={<AutomationView />} />
          <Route path="/connections" element={<ConnectionsView />} />
          <Route path="/documents" element={<DocumentsView />} />
          <Route path="/intelligence" element={<IntelligenceView />} />
          <Route path="/audit" element={<AuditView />} />
          <Route path="/settings" element={<SettingsView />} />
        </Routes>
      </Chrome>
    </SessionProvider>
  );
}
