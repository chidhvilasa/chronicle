import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TopNav } from "../TopNav";
import { useAppStore } from "../../store/useAppStore";
import { chronicleApi } from "../../api/client";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    chronicleApi: { checkHealth: vi.fn() },
  };
});

const initialState = useAppStore.getState();

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.checkHealth).mockReset();
});

describe("TopNav", () => {
  it("renders the brand and all three panel tabs", () => {
    vi.mocked(chronicleApi.checkHealth).mockResolvedValue({ status: "ok", version: "0.3.0" });
    render(<TopNav />);

    expect(screen.getByText("Chronicle")).toBeInTheDocument();
    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText("Inspector")).toBeInTheDocument();
    expect(screen.getByText("Diff")).toBeInTheDocument();
  });

  it("switches the active panel when a tab is clicked", () => {
    vi.mocked(chronicleApi.checkHealth).mockResolvedValue({ status: "ok", version: "0.3.0" });
    render(<TopNav />);

    screen.getByText("Diff").click();
    expect(useAppStore.getState().activePanel).toBe("diff");
  });

  it("shows a green connection dot when the server is reachable", async () => {
    vi.mocked(chronicleApi.checkHealth).mockResolvedValue({ status: "ok", version: "0.3.0" });
    render(<TopNav />);

    await waitFor(() => {
      expect(screen.getByTestId("connection-status")).toHaveClass("connected");
    });
  });

  it("shows a red connection dot when the server is unreachable", async () => {
    vi.mocked(chronicleApi.checkHealth).mockRejectedValue(new Error("unreachable"));
    render(<TopNav />);

    await waitFor(() => {
      expect(screen.getByTestId("connection-status")).toHaveClass("disconnected");
    });
  });

  it("renders a settings icon with no functionality", () => {
    vi.mocked(chronicleApi.checkHealth).mockResolvedValue({ status: "ok", version: "0.3.0" });
    render(<TopNav />);

    expect(screen.getByLabelText("Settings")).toBeInTheDocument();
  });
});
