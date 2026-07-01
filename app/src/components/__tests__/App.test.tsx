import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { useAppStore } from "../../store/useAppStore";
import { chronicleApi } from "../../api/client";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    chronicleApi: {
      listRuns: vi.fn(),
      checkHealth: vi.fn(),
      getRunTimeline: vi.fn(),
      listRunEvents: vi.fn(),
    },
  };
});

const initialState = useAppStore.getState();

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.listRuns).mockResolvedValue([]);
  vi.mocked(chronicleApi.checkHealth).mockResolvedValue({ status: "ok", version: "0.3.0" });
});

describe("App", () => {
  it("renders the three-panel layout: run list, main panel, detail inspector", async () => {
    render(<App />);

    expect(screen.getByTestId("top-nav")).toBeInTheDocument();
    expect(screen.getByTestId("run-list")).toBeInTheDocument();
    expect(screen.getByTestId("main-panel")).toBeInTheDocument();
    expect(screen.getByTestId("detail-inspector")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
    });
  });

  it("does not show a server-startup error banner outside the Tauri runtime", () => {
    render(<App />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
