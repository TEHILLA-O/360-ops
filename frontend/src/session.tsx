import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const KEY = "opspilot.persona";

type SessionValue = {
  personaId: string;
  setPersonaId: (id: string) => void;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [personaId, setPersonaId] = useState(() => localStorage.getItem(KEY) || "maya.chen");
  useEffect(() => {
    localStorage.setItem(KEY, personaId);
  }, [personaId]);
  const value = useMemo(() => ({ personaId, setPersonaId }), [personaId]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("Session missing");
  return value;
}
