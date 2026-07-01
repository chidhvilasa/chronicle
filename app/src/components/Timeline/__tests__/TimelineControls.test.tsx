import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TimelineControls } from "../TimelineControls";

describe("TimelineControls", () => {
  it("calls onZoomIn, onZoomOut, and onFitToScreen when their buttons are clicked", () => {
    const onZoomIn = vi.fn();
    const onZoomOut = vi.fn();
    const onFitToScreen = vi.fn();
    render(
      <TimelineControls
        filter="all"
        onFilterChange={vi.fn()}
        onZoomIn={onZoomIn}
        onZoomOut={onZoomOut}
        onFitToScreen={onFitToScreen}
      />
    );

    screen.getByLabelText("Zoom in").click();
    screen.getByLabelText("Zoom out").click();
    screen.getByLabelText("Fit to screen").click();

    expect(onZoomIn).toHaveBeenCalledTimes(1);
    expect(onZoomOut).toHaveBeenCalledTimes(1);
    expect(onFitToScreen).toHaveBeenCalledTimes(1);
  });

  it("renders all four filter options and reports changes", () => {
    const onFilterChange = vi.fn();
    render(
      <TimelineControls
        filter="all"
        onFilterChange={onFilterChange}
        onZoomIn={vi.fn()}
        onZoomOut={vi.fn()}
        onFitToScreen={vi.fn()}
      />
    );

    const select = screen.getByLabelText("Filter segments") as HTMLSelectElement;
    expect(select.options).toHaveLength(4);

    select.value = "errors";
    select.dispatchEvent(new Event("change", { bubbles: true }));

    expect(onFilterChange).toHaveBeenCalledWith("errors");
  });
});
