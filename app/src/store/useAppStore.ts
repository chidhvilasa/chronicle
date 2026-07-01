import { create } from "zustand";
import type { DetailItem, Run } from "../types";

export type PanelId = "timeline" | "inspector" | "diff";

interface AppState {
  runs: Run[];
  selectedRunId: string | null;
  loading: boolean;
  error: string | null;
  activePanel: PanelId;
  selectedDetail: DetailItem | null;
  setRuns: (runs: Run[]) => void;
  selectRun: (runId: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setActivePanel: (panel: PanelId) => void;
  setSelectedDetail: (item: DetailItem | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  runs: [],
  selectedRunId: null,
  loading: false,
  error: null,
  activePanel: "timeline",
  selectedDetail: null,
  setRuns: (runs) => set({ runs }),
  selectRun: (runId) => set({ selectedRunId: runId, selectedDetail: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setActivePanel: (activePanel) => set({ activePanel }),
  setSelectedDetail: (selectedDetail) => set({ selectedDetail }),
}));
