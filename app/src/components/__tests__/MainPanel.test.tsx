import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MainPanel } from "../MainPanel";
import { useAppStore } from "../../store/useAppStore";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    chronicleApi: { getRunTimeline: vi.fn(), listRunEvents: vi.fn(), listTests: vi.fn().mockResolvedValue([]) },
  };
});

const initialState = useAppStore.getState();

beforeEach(() => {
  useAppStore.setState(initialState, true);
});

describe("MainPanel", () => {
  it("renders the timeline panel by default", () => {
    render(<MainPanel />);
    expect(screen.getByText(/select a run to see its timeline/i)).toBeInTheDocument();
  });

  it("renders the inspector panel when activePanel is inspector", () => {
    useAppStore.getState().setActivePanel("inspector");
    render(<MainPanel />);
    expect(screen.getByText(/select a run to inspect its events/i)).toBeInTheDocument();
  });

  it("renders the diff panel when activePanel is diff", () => {
    useAppStore.getState().setActivePanel("diff");
    render(<MainPanel />);
    expect(screen.getByTestId("diff-root")).toBeInTheDocument();
  });

  it("renders the tests panel when activePanel is tests", () => {
    useAppStore.getState().setActivePanel("tests");
    render(<MainPanel />);
    expect(screen.getByTestId("tests-root")).toBeInTheDocument();
  });
});
