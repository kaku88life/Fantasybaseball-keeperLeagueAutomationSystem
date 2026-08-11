"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import StatcastPanel from "@/components/StatcastPanel";
import { getPlayerStats } from "@/lib/api";
import type { PlayerStats } from "@/types";

interface PlayerStatsModalProps {
  playerName: string;
  position: string;
  onClose: () => void;
}

// Level display order
const LEVEL_ORDER = ["MLB", "AAA", "AA", "A+", "A", "ROK"] as const;

// Level color styling
const LEVEL_COLORS: Record<string, { bg: string; text: string }> = {
  MLB: { bg: "bg-blue-100", text: "text-blue-700" },
  AAA: { bg: "bg-emerald-100", text: "text-emerald-700" },
  AA: { bg: "bg-amber-100", text: "text-amber-700" },
  "A+": { bg: "bg-orange-100", text: "text-orange-700" },
  A: { bg: "bg-purple-100", text: "text-purple-700" },
  ROK: { bg: "bg-gray-100", text: "text-gray-500" },
};

export default function PlayerStatsModal({
  playerName,
  position,
  onClose,
}: PlayerStatsModalProps) {
  const [stats, setStats] = useState<PlayerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [levelFilter, setLevelFilter] = useState("ALL");

  useEffect(() => {
    setLoading(true);
    setError("");
    setLevelFilter("ALL");
    getPlayerStats(playerName, position)
      .then((data) => setStats(data))
      .catch((e) => setError(e.message || "Failed to load player stats"))
      .finally(() => setLoading(false));
  }, [playerName, position]);

  // ESC key to close
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  // Collect all available levels from stats data
  const availableLevels = useMemo(() => {
    if (!stats) return [];
    const levels = new Set<string>();
    for (const s of stats.hitting) {
      if (s.level) levels.add(s.level);
    }
    for (const s of stats.pitching) {
      if (s.level) levels.add(s.level);
    }
    // Sort by defined order
    return LEVEL_ORDER.filter((l) => levels.has(l));
  }, [stats]);

  // Filtered stats
  const filteredHitting = useMemo(() => {
    if (!stats) return [];
    if (levelFilter === "ALL") return stats.hitting;
    return stats.hitting.filter((s) => s.level === levelFilter);
  }, [stats, levelFilter]);

  const filteredPitching = useMemo(() => {
    if (!stats) return [];
    if (levelFilter === "ALL") return stats.pitching;
    return stats.pitching.filter((s) => s.level === levelFilter);
  }, [stats, levelFilter]);

  // Level badge (compact inline)
  const levelBadge = (level?: string) => {
    const lv = level || "MLB";
    const colors = LEVEL_COLORS[lv] ?? { bg: "bg-gray-100", text: "text-gray-500" };
    return (
      <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${colors.bg} ${colors.text}`}>
        {lv}
      </span>
    );
  };

  // Row background for minor league seasons
  const rowBg = (level?: string) => {
    if (!level || level === "MLB") return "hover:bg-gray-50";
    return "bg-gray-50/50 hover:bg-gray-100/70";
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={handleBackdropClick}
    >
      <div className="relative max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-xl bg-white shadow-2xl sm:max-h-[85vh]">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 rounded-full bg-gray-100 p-1.5 text-gray-500 hover:bg-gray-200 hover:text-gray-700"
          aria-label="Close"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </button>

        {/* Loading state */}
        {loading && (
          <div className="p-8">
            <div className="mb-4 h-8 w-48 animate-pulse rounded bg-gray-200" />
            <div className="mb-2 h-4 w-64 animate-pulse rounded bg-gray-100" />
            <div className="mt-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="h-8 animate-pulse rounded bg-gray-100"
                />
              ))}
            </div>
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div className="p-8">
            <h3 className="mb-2 text-lg font-bold text-gray-800">
              {playerName}
            </h3>
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium">
                無法取得球員成績 Unable to load stats
              </p>
              <p className="mt-1 text-xs text-red-500">{error}</p>
            </div>
          </div>
        )}

        {/* Stats content */}
        {!loading && stats && (
          <div className="overflow-y-auto" style={{ maxHeight: "90vh" }}>
            {/* Header */}
            <div className="sticky top-0 z-[1] border-b bg-white px-4 py-3 sm:px-6 sm:py-4">
              <h3 className="text-lg font-bold text-gray-800 sm:text-xl">{stats.name}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-gray-500">
                {stats.current_team && (
                  <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-700">
                    {stats.current_team}
                  </span>
                )}
                {stats.primary_position && (
                  <span className="rounded bg-gray-100 px-2 py-0.5">
                    {stats.primary_position}
                  </span>
                )}
                {stats.age && <span>{stats.age} 歲</span>}
                {stats.bat_side && <span>打: {stats.bat_side}</span>}
                {stats.pitch_hand && <span>投: {stats.pitch_hand}</span>}
              </div>

              {/* Rookie Eligibility Status */}
              {stats.rookie_thresholds && (
                <div className={`mt-3 rounded-lg border px-4 py-3 ${
                  stats.rookie_eligible
                    ? "border-green-200 bg-green-50"
                    : "border-orange-200 bg-orange-50"
                }`}>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-semibold ${
                      stats.rookie_eligible ? "text-green-700" : "text-orange-700"
                    }`}>
                      {stats.rookie_eligible
                        ? "符合新秀資格 Rookie Eligible"
                        : "已超過新秀門檻 Exceeded Rookie Threshold"}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-4 text-xs text-gray-600">
                    <span className={stats.rookie_thresholds.exceeded_pa ? "font-bold text-orange-600" : ""}>
                      生涯打席 PA: {stats.career_pa}
                      <span className="text-gray-400">
                        /{stats.rookie_thresholds.pa_threshold}
                      </span>
                    </span>
                    <span className={stats.rookie_thresholds.exceeded_ip ? "font-bold text-orange-600" : ""}>
                      生涯投球局數 IP: {stats.career_ip}
                      <span className="text-gray-400">
                        /{stats.rookie_thresholds.ip_threshold}
                      </span>
                    </span>
                  </div>
                </div>
              )}

              {/* Level filter dropdown */}
              {availableLevels.length > 1 && (
                <div className="mt-3 flex items-center gap-2">
                  <label className="text-xs font-medium text-gray-500">層級篩選:</label>
                  <select
                    value={levelFilter}
                    onChange={(e) => setLevelFilter(e.target.value)}
                    className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="ALL">全部層級 ({stats.hitting.length + stats.pitching.length})</option>
                    {availableLevels.map((lv) => {
                      const count =
                        stats.hitting.filter((s) => s.level === lv).length +
                        stats.pitching.filter((s) => s.level === lv).length;
                      return (
                        <option key={lv} value={lv}>
                          {lv} ({count})
                        </option>
                      );
                    })}
                  </select>
                </div>
              )}
            </div>

            <div className="px-4 py-3 space-y-6 sm:px-6 sm:py-4">
              {/* Statcast: recent form vs season baseline */}
              <StatcastPanel
                mlbId={stats.mlb_id}
                position={stats.primary_position || position}
              />

              {/* Hitting stats */}
              {filteredHitting.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold text-gray-700">
                    打擊成績 Hitting Stats
                  </h4>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full min-w-[650px] text-xs sm:text-sm">
                      <thead className="bg-gray-50 text-[10px] text-gray-500 sm:text-xs">
                        <tr>
                          <th className="px-1.5 py-1.5 text-left sm:px-2 sm:py-2">Year</th>
                          <th className="px-1.5 py-1.5 text-center sm:px-2 sm:py-2">Lv</th>
                          <th className="px-1.5 py-1.5 text-left sm:px-2 sm:py-2">Team</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">G</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">PA</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">AB</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">H</th>
                          <th className="px-1.5 py-1.5 text-right font-bold sm:px-2 sm:py-2">HR</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">RBI</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">R</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">SB</th>
                          <th className="px-1.5 py-1.5 text-right font-bold sm:px-2 sm:py-2">AVG</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">OBP</th>
                          <th className="px-1.5 py-1.5 text-right font-bold sm:px-2 sm:py-2">OPS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredHitting.map((s, i) => (
                          <tr
                            key={`${s.season}-${s.team}-${s.level}-${i}`}
                            className={`border-t ${rowBg(s.level)}`}
                          >
                            <td className="px-2 py-1.5 font-medium">
                              {s.season}
                            </td>
                            <td className="px-2 py-1.5 text-center">
                              {levelBadge(s.level)}
                            </td>
                            <td className="px-2 py-1.5 text-gray-600 truncate max-w-[120px]">
                              {s.team}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.games}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.plate_appearances}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.at_bats}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.hits}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold">
                              {s.home_runs}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.rbi}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.runs}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.stolen_bases}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold">
                              {s.avg}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.obp}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold">
                              {s.ops}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Pitching stats */}
              {filteredPitching.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold text-gray-700">
                    投球成績 Pitching Stats
                  </h4>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full min-w-[650px] text-xs sm:text-sm">
                      <thead className="bg-gray-50 text-[10px] text-gray-500 sm:text-xs">
                        <tr>
                          <th className="px-1.5 py-1.5 text-left sm:px-2 sm:py-2">Year</th>
                          <th className="px-1.5 py-1.5 text-center sm:px-2 sm:py-2">Lv</th>
                          <th className="px-1.5 py-1.5 text-left sm:px-2 sm:py-2">Team</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">G</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">GS</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">W</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">L</th>
                          <th className="px-1.5 py-1.5 text-right font-bold sm:px-2 sm:py-2">ERA</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">IP</th>
                          <th className="px-1.5 py-1.5 text-right font-bold sm:px-2 sm:py-2">K</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">BB</th>
                          <th className="px-1.5 py-1.5 text-right font-bold sm:px-2 sm:py-2">WHIP</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">SV</th>
                          <th className="px-1.5 py-1.5 text-right sm:px-2 sm:py-2">HLD</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPitching.map((s, i) => (
                          <tr
                            key={`${s.season}-${s.team}-${s.level}-${i}`}
                            className={`border-t ${rowBg(s.level)}`}
                          >
                            <td className="px-2 py-1.5 font-medium">
                              {s.season}
                            </td>
                            <td className="px-2 py-1.5 text-center">
                              {levelBadge(s.level)}
                            </td>
                            <td className="px-2 py-1.5 text-gray-600 truncate max-w-[120px]">
                              {s.team}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.games}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.games_started}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.wins}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.losses}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold">
                              {s.era}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.innings_pitched}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold">
                              {s.strikeouts}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.walks}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold">
                              {s.whip}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.saves}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.holds}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* No stats available */}
              {filteredHitting.length === 0 && filteredPitching.length === 0 && (
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center text-sm text-gray-500">
                  {levelFilter === "ALL"
                    ? "無成績紀錄 No stats available (MLB / MiLB)"
                    : `${levelFilter} 層級無成績紀錄`}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
