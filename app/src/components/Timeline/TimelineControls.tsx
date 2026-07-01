export type SegmentFilter = "all" | "llm" | "tools" | "errors";

interface TimelineControlsProps {
  filter: SegmentFilter;
  onFilterChange: (filter: SegmentFilter) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitToScreen: () => void;
}

const FILTER_OPTIONS: { value: SegmentFilter; label: string }[] = [
  { value: "all", label: "Show all" },
  { value: "llm", label: "LLM only" },
  { value: "tools", label: "Tools only" },
  { value: "errors", label: "Errors only" },
];

/** Zoom in/out/fit buttons and a segment-type filter dropdown for the timeline. */
export function TimelineControls({
  filter,
  onFilterChange,
  onZoomIn,
  onZoomOut,
  onFitToScreen,
}: TimelineControlsProps) {
  return (
    <div className="timeline-controls" data-testid="timeline-controls">
      <div className="timeline-zoom-controls">
        <button type="button" onClick={onZoomIn} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={onZoomOut} aria-label="Zoom out">
          −
        </button>
        <button type="button" onClick={onFitToScreen} aria-label="Fit to screen">
          Fit
        </button>
      </div>
      <label className="timeline-filter">
        Filter
        <select
          value={filter}
          onChange={(event) => onFilterChange(event.target.value as SegmentFilter)}
          aria-label="Filter segments"
        >
          {FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
