import { create } from "zustand";
import type { DetailItem, Run } from "../types";

export type PanelId = "timeline" | "inspector" | "diff";

export type InspectorTab = "event" | "agent" | "tools";

interface AppState {
  runs: Run[];
  selectedRunId: string | null;
  loading: boolean;
  error: string | null;
  activePanel: PanelId;
  selectedDetail: DetailItem | null;
  inspectorTab: InspectorTab;
  selectedAgentName: string | null;
  selectedToolName: string | null;
  setRuns: (runs: Run[]) => void;
  selectRun: (runId: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setActivePanel: (panel: PanelId) => void;
  setInspectorTab: (tab: InspectorTab) => void;
  /** Sets the selected event/segment and switches the right panel to the Event tab. */
  selectDetail: (item: DetailItem | null) => void;
  /** Sets the selected agent and switches the right panel to the Agent tab. */
  selectAgent: (agentName: string | null) => void;
  selectTool: (toolName: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  runs: [],
  selectedRunId: null,
  loading: false,
  error: null,
  activePanel: "timeline",
  selectedDetail: null,
  inspectorTab: "event",
  selectedAgentName: null,
  selectedToolName: null,
  setRuns: (runs) => set({ runs }),
  selectRun: (runId) =>
    set({
      selectedRunId: runId,
      selectedDetail: null,
      selectedAgentName: null,
      selectedToolName: null,
    }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setActivePanel: (activePanel) => set({ activePanel }),
  setInspectorTab: (inspectorTab) => set({ inspectorTab }),
  selectDetail: (selectedDetail) => set({ selectedDetail, inspectorTab: "event" }),
  selectAgent: (selectedAgentName) => set({ selectedAgentName, inspectorTab: "agent" }),
  selectTool: (selectedToolName) => set({ selectedToolName }),
}));
