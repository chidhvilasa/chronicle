import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PeriodSelector } from "../PeriodSelector";

describe("PeriodSelector", () => {
  it("renders all three range buttons with the current value active", () => {
    render(<PeriodSelector value="30D" onChange={vi.fn()} />);

    expect(screen.getByText("7D")).toBeInTheDocument();
    expect(screen.getByText("30D").className).toContain("active");
    expect(screen.getByText("90D").className).not.toContain("active");
  });

  it("calls onChange with the clicked range", () => {
    const onChange = vi.fn();
    render(<PeriodSelector value="30D" onChange={onChange} />);

    fireEvent.click(screen.getByText("7D"));

    expect(onChange).toHaveBeenCalledWith("7D");
  });
});
