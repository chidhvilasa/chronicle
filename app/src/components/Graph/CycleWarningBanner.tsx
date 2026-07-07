/** Shown above the graph when the run's metadata reports a cycle (an agent loop). */
export function CycleWarningBanner() {
  return (
    <div className="graph-cycle-banner" role="alert" data-testid="graph-cycle-banner">
      Cycle detected in this run. Agent loop may indicate unintended behavior.{" "}
      <a href="https://docs.chronicle.dev/execution-graph#cycles" target="_blank" rel="noreferrer">
        Learn more
      </a>
    </div>
  );
}
