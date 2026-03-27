/**
 * Shared utilities for MLB team distribution analysis.
 */

/**
 * Get Tailwind badge classes based on player count threshold.
 * - 5+ players: green (eligible for same-team bonus)
 * - 3+ players: amber (close to bonus)
 * - 2+ players: gray (default)
 */
export function mlbTeamBadgeColor(count: number): string {
  if (count >= 5) return "bg-green-200 text-green-800";
  if (count >= 3) return "bg-amber-200 text-amber-800";
  return "bg-gray-200 text-gray-600";
}

/**
 * Count occurrences of MLB teams from a player list.
 * Returns sorted array of [team, count] tuples (descending by count).
 *
 * @param players - Array with mlb_team property
 * @param minCount - Minimum count to include (default: 2)
 * @param maxResults - Maximum entries to return (default: 5)
 */
export function getTopMLBTeams<P extends { mlb_team?: string }>(
  players: P[],
  minCount: number = 2,
  maxResults: number = 5,
): [string, number][] {
  const counts: Record<string, number> = {};
  for (const p of players) {
    const t = p.mlb_team || "???";
    counts[t] = (counts[t] || 0) + 1;
  }
  return Object.entries(counts)
    .filter(([, c]) => c >= minCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxResults);
}
