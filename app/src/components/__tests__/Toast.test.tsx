import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toast } from "../Toast";
import { useAppStore } from "../../store/useAppStore";
import { TOAST_DURATION_MS } from "../../config";

const initialState = useAppStore.getState();

beforeEach(() => {
  useAppStore.setState(initialState, true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Toast", () => {
  it("renders nothing when there is no toast", () => {
    render(<Toast />);
    expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
  });

  it("shows the toast message and an action button when set", () => {
    useAppStore.getState().showToast({ message: "Replay complete. Compare with original?", actionLabel: "Compare", onAction: vi.fn() });
    render(<Toast />);

    expect(screen.getByTestId("toast")).toHaveTextContent("Replay complete. Compare with original?");
    expect(screen.getByRole("button", { name: "Compare" })).toBeInTheDocument();
  });

  it("calls onAction and dismisses when the action button is clicked", () => {
    const onAction = vi.fn();
    useAppStore.getState().showToast({ message: "Done", actionLabel: "Compare", onAction });
    render(<Toast />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(onAction).toHaveBeenCalled();
    expect(useAppStore.getState().toast).toBeNull();
  });

  it("dismisses when the close button is clicked", () => {
    useAppStore.getState().showToast({ message: "Done" });
    render(<Toast />);

    fireEvent.click(screen.getByLabelText("Dismiss"));

    expect(useAppStore.getState().toast).toBeNull();
  });

  it("auto-dismisses after the configured duration", () => {
    vi.useFakeTimers();
    useAppStore.getState().showToast({ message: "Done" });
    render(<Toast />);

    act(() => {
      vi.advanceTimersByTime(TOAST_DURATION_MS);
    });

    expect(useAppStore.getState().toast).toBeNull();
  });
});
