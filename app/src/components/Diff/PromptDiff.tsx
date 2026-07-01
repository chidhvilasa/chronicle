import { diffChars } from "diff";

interface PromptDiffProps {
  promptA: string;
  promptB: string;
}

/** Character-level diff of two llm_call prompts: additions green, removals red, unchanged gray. */
export function PromptDiff({ promptA, promptB }: PromptDiffProps) {
  const changes = diffChars(promptA, promptB);

  return (
    <pre className="code-block prompt-diff" data-testid="prompt-diff">
      {changes.map((change, index) => (
        <span
          key={index}
          className={change.added ? "diff-added" : change.removed ? "diff-removed" : "diff-same"}
        >
          {change.value}
        </span>
      ))}
    </pre>
  );
}
