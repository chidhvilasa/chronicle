import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TokenUsageSummary } from "../TokenUsageSummary";
import type { TimelineLane } from "../../../types";

describe("TokenUsageSummary", () => {
  it("shows zero totals and zero cost when there is no token usage", () => {
    const lanes: TimelineLane[] = [
      { agent_name: "agent-a", segments: [{ type: "tool_call", start_time_ms: 0, duration_ms: 10, label: "search", token_usage: null }] },
    ];
    render(<TokenUsageSummary lanes={lanes} />);

    const summary = screen.getByTestId("token-usage-summary");
    expect(summary.textContent).toContain("Input tokens: 0");
    expect(summary.textContent).toContain("Output tokens: 0");
    expect(screen.getByText("$0.0000")).toBeInTheDocument();
  });

  it("sums input/output tokens across lanes and segments and estimates cost", () => {
    const lanes: TimelineLane[] = [
      {
        agent_name: "agent-a",
        segments: [
          {
            type: "llm_call",
            start_time_ms: 0,
            duration_ms: 100,
            label: "gpt-4o",
            token_usage: { input_tokens: 1000, output_tokens: 500 },
          },
        ],
      },
      {
        agent_name: "agent-b",
        segments: [
          {
            type: "llm_call",
            start_time_ms: 0,
            duration_ms: 100,
            label: "gpt-4o",
            token_usage: { input_tokens: 2000, output_tokens: 1000 },
          },
        ],
      },
    ];
    render(<TokenUsageSummary lanes={lanes} />);

    // 3000 input * 0.000003 + 1500 output * 0.000015 = 0.009 + 0.0225 = 0.0315
    expect(screen.getByText("3,000")).toBeInTheDocument();
    expect(screen.getByText("1,500")).toBeInTheDocument();
    expect(screen.getByText("$0.0315")).toBeInTheDocument();
  });
});
