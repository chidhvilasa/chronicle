/** Formats a token count with a K/M suffix, e.g. 1234 -> "1.2K", 2_500_000 -> "2.5M". */
export function formatTokenCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

/** Formats an estimated USD cost as "$X.XX". */
export function formatCostUsd(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

/** Formats a millisecond duration as "Xms" / "Xs" / "Xm". */
export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

/** Formats a 0-1 fraction as a percentage string, e.g. 0.052 -> "5.2%". */
export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}
