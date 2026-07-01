import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromptDiff } from "../PromptDiff";

describe("PromptDiff", () => {
  it("renders unchanged text with no added/removed class when prompts are identical", () => {
    render(<PromptDiff promptA="hello world" promptB="hello world" />);
    const container = screen.getByTestId("prompt-diff");
    expect(container.querySelectorAll(".diff-added")).toHaveLength(0);
    expect(container.querySelectorAll(".diff-removed")).toHaveLength(0);
    expect(container.textContent).toBe("hello world");
  });

  it("marks inserted characters as additions", () => {
    render(<PromptDiff promptA="cat" promptB="cats" />);
    const container = screen.getByTestId("prompt-diff");
    const added = container.querySelectorAll(".diff-added");
    expect(added).toHaveLength(1);
    expect(added[0].textContent).toBe("s");
  });

  it("marks removed characters as removals", () => {
    render(<PromptDiff promptA="cats" promptB="cat" />);
    const container = screen.getByTestId("prompt-diff");
    const removed = container.querySelectorAll(".diff-removed");
    expect(removed).toHaveLength(1);
    expect(removed[0].textContent).toBe("s");
  });

  it("shows a mix of same, added, and removed spans for a substitution", () => {
    render(<PromptDiff promptA="What's the weather?" promptB="What's the forecast?" />);
    const container = screen.getByTestId("prompt-diff");
    expect(container.querySelectorAll(".diff-same").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".diff-added").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".diff-removed").length).toBeGreaterThan(0);
    expect(container.textContent).toContain("forecast");
  });

  it("handles an empty prompt on either side", () => {
    render(<PromptDiff promptA="" promptB="new text" />);
    const container = screen.getByTestId("prompt-diff");
    expect(container.textContent).toBe("new text");
  });
});
