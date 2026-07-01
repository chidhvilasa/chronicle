import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DiffPanel } from "../DiffPanel";

describe("DiffPanel", () => {
  it("renders a placeholder message", () => {
    render(<DiffPanel />);
    expect(screen.getByTestId("diff-panel")).toBeInTheDocument();
    expect(screen.getByText(/implemented yet/i)).toBeInTheDocument();
  });
});
