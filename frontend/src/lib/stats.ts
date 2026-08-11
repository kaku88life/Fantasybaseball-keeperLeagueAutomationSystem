/**
 * Shared stat column definitions and formatting for player stats tables.
 *
 * Used by: players/page.tsx, draft-strategy/page.tsx
 */

export const HITTING_COLS: Array<{ key: string; label: string }> = [
  { key: "ab", label: "AB" },
  { key: "r", label: "R" },
  { key: "h", label: "H" },
  { key: "hr", label: "HR" },
  { key: "rbi", label: "RBI" },
  { key: "sb", label: "SB" },
  { key: "avg", label: "AVG" },
  { key: "ops", label: "OPS" },
];

export const PITCHING_COLS: Array<{ key: string; label: string }> = [
  { key: "ip", label: "IP" },
  { key: "w", label: "W" },
  { key: "sv", label: "SV" },
  { key: "hld", label: "HLD" },
  { key: "k", label: "K" },
  { key: "era", label: "ERA" },
  { key: "whip", label: "WHIP" },
  { key: "qs", label: "QS" },
];

/** Rate stats that should display 3 decimal places (e.g. .297) */
const RATE_3 = new Set(["avg", "ops"]);
/** Rate stats that should display 2 decimal places (e.g. 3.42) */
const RATE_2 = new Set(["era", "whip"]);

/**
 * Format a stat value for display.
 * - AVG/OPS: .XXX (3 decimals, strip leading zero)
 * - ERA/WHIP: X.XX (2 decimals)
 * - IP: X.X (1 decimal)
 * - Others: integer
 */
export function formatStat(val: number | undefined | null, key: string): string {
  if (val == null) return "-";
  if (RATE_3.has(key)) return val.toFixed(3).replace(/^0/, "");
  if (RATE_2.has(key)) return val.toFixed(2);
  if (key === "ip") return val.toFixed(1);
  return String(val);
}

// ========== Advanced (Statcast) columns ==========

/**
 * Statcast columns shown when the 進階數據 toggle is on.
 * Split by role because the same header would mean different things for a
 * batter and a pitcher (xwOBA produced vs xwOBA allowed).
 */
export const ADV_BATTING_COLS: Array<{ key: string; label: string; glossary: string }> = [
  { key: "xwoba", label: "xwOBA", glossary: "xwoba" },
  { key: "woba", label: "wOBA", glossary: "woba" },
  { key: "barrel_rate", label: "Brl%", glossary: "barrel_rate" },
  { key: "hard_hit_rate", label: "HH%", glossary: "hard_hit_rate" },
  { key: "avg_ev", label: "EV", glossary: "avg_ev" },
];

export const ADV_PITCHING_COLS: Array<{ key: string; label: string; glossary: string }> = [
  { key: "xwoba", label: "xwOBA-A", glossary: "xwoba_against" },
  { key: "whiff_rate", label: "Whiff%", glossary: "whiff_rate" },
  { key: "avg_fastball_velo", label: "Velo", glossary: "velo" },
  { key: "barrel_rate", label: "Brl%-A", glossary: "barrel_rate_against" },
  { key: "hard_hit_rate", label: "HH%-A", glossary: "hard_hit_rate_against" },
];

/** Format one Statcast value for the compact table cell. */
export function formatAdvStat(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (key === "xwoba" || key === "woba") {
    const text = value.toFixed(3);
    return text.startsWith("0.") ? text.slice(1) : text;
  }
  if (key === "avg_ev" || key === "avg_fastball_velo") return value.toFixed(1);
  return `${value}`;
}

/**
 * How far a hitter's actual output trails his contact quality.
 * Positive = under-performing = the buy window is still open.
 */
export function buySignalGap(
  xwoba: number | null | undefined,
  woba: number | null | undefined,
): number | null {
  if (xwoba === null || xwoba === undefined) return null;
  if (woba === null || woba === undefined) return null;
  return xwoba - woba;
}

/** Buy-signal strength thresholds, shared by the table and its legend. */
export const BUY_SIGNAL_STRONG = 0.06;
export const BUY_SIGNAL_MILD = 0.03;

export function buySignalLevel(gap: number | null): "strong" | "mild" | "none" {
  if (gap === null) return "none";
  if (gap >= BUY_SIGNAL_STRONG) return "strong";
  if (gap >= BUY_SIGNAL_MILD) return "mild";
  return "none";
}
