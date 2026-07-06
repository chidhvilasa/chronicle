import { useState } from "react";
import { TestList } from "./TestList";
import { TestResultPanel } from "./TestResult";

/** Tests tab: the test list by default, or one test's detail view once a row is clicked. */
export function Tests() {
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);

  return (
    <div className="tests-root" data-testid="tests-root">
      {selectedTestId === null ? (
        <TestList onSelectTest={setSelectedTestId} />
      ) : (
        <TestResultPanel testId={selectedTestId} onBack={() => setSelectedTestId(null)} />
      )}
    </div>
  );
}
