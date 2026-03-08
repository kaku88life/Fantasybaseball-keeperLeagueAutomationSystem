"use client";

import { useCallback, useEffect, useState } from "react";
import { getPlayerStats } from "@/lib/api";
import type { PlayerStats } from "@/types";

interface PlayerStatsModalProps {
  playerName: string;
  position: string;
  onClose: () => void;
}

export default function PlayerStatsModal({
  playerName,
  position,
  onClose,
}: PlayerStatsModalProps) {
  const [stats, setStats] = useState<PlayerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={handleBackdropClick}
    >
      <div className="relative max-h-[85vh] w-full max-w-3xl overflow-hidden rounded-xl bg-white shadow-2xl">
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
          <div className="overflow-y-auto" style={{ maxHeight: "85vh" }}>
            {/* Header */}
            <div className="sticky top-0 z-[1] border-b bg-white px-6 py-4">
              <h3 className="text-xl font-bold text-gray-800">{stats.name}</h3>
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
            </div>

            <div className="px-6 py-4 space-y-6">
              {/* Hitting stats */}
              {stats.hitting.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold text-gray-700">
                    打擊成績 Hitting Stats
                  </h4>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 text-xs text-gray-500">
                        <tr>
                          <th className="px-2 py-2 text-left">Year</th>
                          <th className="px-2 py-2 text-left">Team</th>
                          <th className="px-2 py-2 text-right">G</th>
                          <th className="px-2 py-2 text-right">AB</th>
                          <th className="px-2 py-2 text-right">H</th>
                          <th className="px-2 py-2 text-right font-bold">HR</th>
                          <th className="px-2 py-2 text-right">RBI</th>
                          <th className="px-2 py-2 text-right">R</th>
                          <th className="px-2 py-2 text-right">SB</th>
                          <th className="px-2 py-2 text-right font-bold">AVG</th>
                          <th className="px-2 py-2 text-right">OBP</th>
                          <th className="px-2 py-2 text-right font-bold">OPS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.hitting.map((s, i) => (
                          <tr
                            key={`${s.season}-${s.team}-${i}`}
                            className="border-t hover:bg-gray-50"
                          >
                            <td className="px-2 py-1.5 font-medium">
                              {s.season}
                            </td>
                            <td className="px-2 py-1.5 text-gray-600 truncate max-w-[120px]">
                              {s.team}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {s.games}
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
              {stats.pitching.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold text-gray-700">
                    投球成績 Pitching Stats
                  </h4>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 text-xs text-gray-500">
                        <tr>
                          <th className="px-2 py-2 text-left">Year</th>
                          <th className="px-2 py-2 text-left">Team</th>
                          <th className="px-2 py-2 text-right">G</th>
                          <th className="px-2 py-2 text-right">GS</th>
                          <th className="px-2 py-2 text-right">W</th>
                          <th className="px-2 py-2 text-right">L</th>
                          <th className="px-2 py-2 text-right font-bold">
                            ERA
                          </th>
                          <th className="px-2 py-2 text-right">IP</th>
                          <th className="px-2 py-2 text-right font-bold">K</th>
                          <th className="px-2 py-2 text-right">BB</th>
                          <th className="px-2 py-2 text-right font-bold">
                            WHIP
                          </th>
                          <th className="px-2 py-2 text-right">SV</th>
                          <th className="px-2 py-2 text-right">HLD</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.pitching.map((s, i) => (
                          <tr
                            key={`${s.season}-${s.team}-${i}`}
                            className="border-t hover:bg-gray-50"
                          >
                            <td className="px-2 py-1.5 font-medium">
                              {s.season}
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
              {stats.hitting.length === 0 && stats.pitching.length === 0 && (
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center text-sm text-gray-500">
                  無 MLB 成績紀錄 No MLB stats available
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
