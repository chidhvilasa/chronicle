import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PromptDetail, PromptSummary } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getRunPrompts: vi.fn(), getRunPrompt: vi.fn(), getPromptsDiff: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { useAppStore } from "../../../store/useAppStore";
import { PromptInspector } from "../PromptInspector";

const initialState = useAppStore.getState();

function makeSummary(overrides: Partial<PromptSummary> = {}): PromptSummary {
  return {
    event_id: "e1",
    step_index: 0,
    agent_name: "agent-a",
    timestamp: 1000,
    total_chars: 20,
    total_tokens: 15,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<PromptDetail> = {}): PromptDetail {
  return {
    event_id: "e1",
    step_index: 0,
    agent_name: "agent-a",
    timestamp: 1000,
    system_prompt: "You are helpful.",
    user_messages: [{ role: "user", content: "hi" }],
    assistant_messages: [{ role: "assistant", content: "hello" }],
    total_chars: 20,
    total_tokens: 15,
    ...overrides,
  };
}

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.getRunPrompts).mockReset();
  vi.mocked(chronicleApi.getRunPrompt).mockReset();
  vi.mocked(chronicleApi.getPromptsDiff).mockReset();
});

describe("PromptInspector", () => {
  it("renders the empty state when no run is selected", () => {
    expect(() => render(<PromptInspector runId={null} />)).not.toThrow();
    expect(screen.getByText("Select a run to inspect its prompts.")).toBeInTheDocument();
  });

  it("renders without crashing with zero prompts", async () => {
    vi.mocked(chronicleApi.getRunPrompts).mockResolvedValue([]);
    expect(() => render(<PromptInspector runId="run-1" />)).not.toThrow();

    await waitFor(() => {
      expect(screen.getByText("No prompts recorded for this run.")).toBeInTheDocument();
    });
  });

  it("renders a prompt list row per summary", async () => {
    vi.mocked(chronicleApi.getRunPrompts).mockResolvedValue([
      makeSummary({ event_id: "e1", step_index: 0 }),
      makeSummary({ event_id: "e2", step_index: 1 }),
    ]);
    render(<PromptInspector runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByText("Step 0")).toBeInTheDocument();
    });
    expect(screen.getByText("Step 1")).toBeInTheDocument();
  });

  it("shows full prompt content when a prompt row is clicked", async () => {
    vi.mocked(chronicleApi.getRunPrompts).mockResolvedValue([makeSummary()]);
    vi.mocked(chronicleApi.getRunPrompt).mockResolvedValue(makeDetail());
    render(<PromptInspector runId="run-1" />);

    fireEvent.click(await screen.findByText("Step 0"));

    await waitFor(() => {
      expect(screen.getByText("You are helpful.")).toBeInTheDocument();
    });
    expect(screen.getByText("hi")).toBeInTheDocument();
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("shows the diff result after comparing with another prompt", async () => {
    vi.mocked(chronicleApi.getRunPrompts).mockResolvedValue([
      makeSummary({ event_id: "e1", step_index: 0 }),
      makeSummary({ event_id: "e2", step_index: 1 }),
    ]);
    vi.mocked(chronicleApi.getRunPrompt).mockResolvedValue(makeDetail());
    vi.mocked(chronicleApi.getPromptsDiff).mockResolvedValue({
      additions: 2,
      deletions: 1,
      unchanged: 10,
      diff_html: '<span class="same">hi</span>',
    });
    useAppStore.setState({
      runs: [
        { run_id: "run-1", started_at: 0, finished_at: 0, framework: null, agent_count: 1, total_tokens: 0, total_cost_usd: 0, status: "running", metadata: {} },
      ],
    });
    render(<PromptInspector runId="run-1" />);

    fireEvent.click(await screen.findByText("Step 0"));
    await waitFor(() => expect(screen.getByText("You are helpful.")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Compare with another prompt" }));
    fireEvent.click(await screen.findByText("Step 1 (agent-a)"));

    await waitFor(() => {
      expect(screen.getByTestId("prompt-diff-result")).toBeInTheDocument();
    });
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
  });
});
