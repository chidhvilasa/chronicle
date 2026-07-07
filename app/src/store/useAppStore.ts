import { create } from "zustand";
import type { DetailItem, Run } from "../types";

export type PanelId = "timeline" | "inspector" | "diff" | "tests" | "performance";

export type InspectorTab = "event" | "agent" | "tools";

export interface DiffPrefill {
  runAId: string;
  runBId: string;
}

export interface Toast {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

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
  diffPrefill: DiffPrefill | null;
  toast: Toast | null;
  /** Set by clicking a tool name in the Performance tab's tools table; narrows the run sidebar. */
  toolNameFilter: string | null;
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
  /** Queues an initial Run A / Run B selection for the Diff tab to pick up once. */
  setDiffPrefill: (prefill: DiffPrefill | null) => void;
  showToast: (toast: Toast) => void;
  dismissToast: () => void;
  setToolNameFilter: (toolName: string | null) => void;
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
  diffPrefill: null,
  toast: null,
  toolNameFilter: null,
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
  setDiffPrefill: (diffPrefill) => set({ diffPrefill }),
  showToast: (toast) => set({ toast }),
  dismissToast: () => set({ toast: null }),
  setToolNameFilter: (toolNameFilter) => set({ toolNameFilter }),
}));
