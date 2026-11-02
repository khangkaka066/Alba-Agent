"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";
import { loadModel, resolveSelection, saveModel } from "@/lib/models.mjs";
import type { ChatModel, SuggestedModel } from "@/lib/models.mjs";

type ModelsValue = {
  models: ChatModel[];
  /** Well-known models offered even before their provider is connected (`connected` says whether they can run now). */
  suggested: SuggestedModel[];
  /** Providers with a working connection: a model id typed for one of them is accepted. */
  reachable: string[];
  /** The model new tasks run on: the remembered choice, else the workspace default. Null when no model is connected. */
  selected: string | null;
  loading: boolean;
  choose: (id: string) => void;
  refresh: () => Promise<void>;
};

const empty: ModelsValue = { models: [], suggested: [], reachable: [], selected: null, loading: false, choose: () => undefined, refresh: async () => undefined };
const ModelContext = createContext<ModelsValue>(empty);

/** The chat models this workspace can run, and the one the user picked. Shared by the header and the prompt bars. */
export function ModelProvider({ token, children }: { token: string; children: React.ReactNode }) {
  const [models, setModels] = useState<ChatModel[]>([]);
  const [suggested, setSuggested] = useState<SuggestedModel[]>([]);
  const [serverDefault, setServerDefault] = useState<string | null>(null);
  const [remembered, setRemembered] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { setRemembered(loadModel(window.localStorage)); }, []);
  const refresh = useCallback(async () => {
    if (!token) { setModels([]); setSuggested([]); setServerDefault(null); return; }
    try {
      const result = await apiRequest<{ models: ChatModel[]; default: string | null; suggested?: SuggestedModel[] }>("/api/v1/settings/chat-models", token);
      setModels(result.models); setSuggested(result.suggested ?? []); setServerDefault(result.default);
    } catch { /* keep the last known list: a failed refresh must not empty the selector */ }
    finally { setLoading(false); }
  }, [token]);
  useEffect(() => {
    const reload = () => void refresh();
    reload();
    const timer = window.setInterval(reload, 60_000);
    window.addEventListener("nexus:ai-changed", reload);
    return () => { window.clearInterval(timer); window.removeEventListener("nexus:ai-changed", reload); };
  }, [refresh]);

  const choose = useCallback((id: string) => { setRemembered(id); saveModel(window.localStorage, id); }, []);
  const reachable = useMemo(() => [...new Set([...models.map((item) => item.provider), ...suggested.filter((item) => item.connected).map((item) => item.provider)])], [models, suggested]);
  const selected = resolveSelection(models, remembered, serverDefault, reachable);
  const value = useMemo(() => ({ models, suggested, reachable, selected, loading, choose, refresh }), [models, suggested, reachable, selected, loading, choose, refresh]);
  return <ModelContext.Provider value={value}>{children}</ModelContext.Provider>;
}

export const useModels = () => useContext(ModelContext);
