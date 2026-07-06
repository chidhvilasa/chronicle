import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listRunSnapshots: vi.fn(), createTest: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { CreateTestModal } from "../CreateTestModal";

const ALL_ASSERTION_TYPES = [
  "output_contains",
  "output_not_contains",
  "output_matches_regex",
  "tool_called",
  "tool_not_called",
  "token_count_under",
  "latency_under_ms",
  "no_errors",
  "custom",
];

beforeEach(() => {
  vi.mocked(chronicleApi.listRunSnapshots).mockReset().mockResolvedValue([
    { snapshot_id: "snap-0", step_index: 0, timestamp: 1000, agent_name: "agent-a", event_id: "evt-1" },
  ]);
  vi.mocked(chronicleApi.createTest).mockReset();
});

describe("CreateTestModal", () => {
  it("renders the source run read-only and loads snapshot options", async () => {
    render(<CreateTestModal sourceRunId="run-1" onClose={vi.fn()} />);

    expect(screen.getByDisplayValue("run-1")).toBeInTheDocument();
    await waitFor(() => {
      expect(chronicleApi.listRunSnapshots).toHaveBeenCalledWith("run-1");
    });
    expect(await screen.findByText(/Step 0 - agent-a/)).toBeInTheDocument();
  });

  it("includes every assertion type in the type dropdown", async () => {
    render(<CreateTestModal sourceRunId="run-1" onClose={vi.fn()} />);

    const select = screen.getByLabelText("Assertion type");
    const options = within(select).getAllByRole("option") as HTMLOptionElement[];
    const values = options.map((option) => option.value);

    for (const assertionType of ALL_ASSERTION_TYPES) {
      expect(values).toContain(assertionType);
    }
  });

  it("hides the target input for no_errors and shows it for other types", () => {
    render(<CreateTestModal sourceRunId="run-1" onClose={vi.fn()} />);

    expect(screen.getByLabelText("Target")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Assertion type"), { target: { value: "no_errors" } });
    expect(screen.queryByLabelText("Target")).not.toBeInTheDocument();
  });

  it("adds and removes assertion rows", () => {
    render(<CreateTestModal sourceRunId="run-1" onClose={vi.fn()} />);

    expect(screen.getAllByTestId("assertion-row")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Add assertion" }));
    expect(screen.getAllByTestId("assertion-row")).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: "Remove assertion" })[0]);
    expect(screen.getAllByTestId("assertion-row")).toHaveLength(1);
  });

  it("requires a test name before saving", () => {
    render(<CreateTestModal sourceRunId="run-1" onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /save test/i }));

    expect(screen.getByText(/test name is required/i)).toBeInTheDocument();
    expect(chronicleApi.createTest).not.toHaveBeenCalled();
  });

  it("saves the test and closes the modal on success", async () => {
    vi.mocked(chronicleApi.createTest).mockResolvedValue({
      test_id: "test-1",
      name: "greets the user",
      source_run_id: "run-1",
      source_snapshot_id: "snap-0",
      assertions: [],
      created_at: 1000,
      last_run_at: null,
      last_result: null,
    });
    const onClose = vi.fn();
    render(<CreateTestModal sourceRunId="run-1" onClose={onClose} />);

    await screen.findByText(/Step 0 - agent-a/);
    fireEvent.change(screen.getByPlaceholderText("agent still greets the user"), {
      target: { value: "greets the user" },
    });
    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: /save test/i }));

    await waitFor(() => {
      expect(chronicleApi.createTest).toHaveBeenCalledWith({
        name: "greets the user",
        sourceRunId: "run-1",
        sourceSnapshotId: "snap-0",
        assertions: [
          { assertion_type: "output_contains", target: "hello", agent_name: null, on_fail: "fail" },
        ],
      });
    });
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("shows a server error message without closing on failure", async () => {
    vi.mocked(chronicleApi.createTest).mockRejectedValue(new Error("boom"));
    const onClose = vi.fn();
    render(<CreateTestModal sourceRunId="run-1" onClose={onClose} />);

    fireEvent.change(screen.getByPlaceholderText("agent still greets the user"), {
      target: { value: "my test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save test/i }));

    await waitFor(() => {
      expect(screen.getByText(/could not create test/i)).toBeInTheDocument();
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});
