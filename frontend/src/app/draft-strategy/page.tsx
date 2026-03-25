"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { getPlayerDatabase, getYears } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import StatusBadge from "@/components/StatusBadge";
import PlayerStatsModal from "@/components/PlayerStatsModal";
import { isBatter, isPitcher } from "@/lib/position";
import type { PlayerDatabaseEntry } from "@/types";

// ── Position filter groups ──
const POSITION_GROUPS = [
  "ALL",
  "BATTER",
  "PITCHER",
  "C",
  "1B",
  "2B",
  "3B",
  "SS",
  "OF",
  "SP",
  "RP",
] as const;

// ── localStorage helpers ──
const STORAGE_KEY = (year: number) => `draft-board-${year}`;

interface DraftBoardStorage {
  year: number;
  updatedAt: string;
  rankings: string[]; // player_key array in custom order
}

function loadCustomOrder(year: number): string[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY(year));
    if (!raw) return null;
    const data: DraftBoardStorage = JSON.parse(raw);
    if (data.year !== year || !Array.isArray(data.rankings)) return null;
    return data.rankings;
  } catch {
    return null;
  }
}

function saveCustomOrder(year: number, order: string[]) {
  if (typeof window === "undefined") return;
  const data: DraftBoardStorage = {
    year,
    updatedAt: new Date().toISOString(),
    rankings: order,
  };
  localStorage.setItem(STORAGE_KEY(year), JSON.stringify(data));
}

// ── Stat column definitions (shared) ──
import { HITTING_COLS, PITCHING_COLS, formatStat } from "@/lib/stats";

// ── Main page component ──
export default function DraftStrategyPage() {
  const { data: years = [] } = useSWR("years", getYears);
  const [selectedYear, setSelectedYear] = useState(0);
  const [positionFilter, setPositionFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [committedSearch, setCommittedSearch] = useState("");
  const [showHitting, setShowHitting] = useState(true);
  const [showPitching, setShowPitching] = useState(true);
  const [modalPlayer, setModalPlayer] = useState<{
    name: string;
    position: string;
  } | null>(null);

  // Custom order state: array of player_keys
  const [customOrder, setCustomOrder] = useState<string[] | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Drag state
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  // Jump-to rank
  const [jumpTarget, setJumpTarget] = useState<{
    playerKey: string;
    value: string;
  } | null>(null);

  // Set default year
  useEffect(() => {
    if (years.length > 0 && selectedYear === 0) {
      setSelectedYear(years[years.length - 1]);
    }
  }, [years, selectedYear]);

  // Fetch ALL players (large page) for the draft board
  const { data: response, isLoading } = useSWR(
    selectedYear ? ["draft-strategy", selectedYear] : null,
    () =>
      getPlayerDatabase(selectedYear, {
        page_size: 500,
        sort_key: "o_rank",
        sort_dir: "asc",
      }),
  );

  const allPlayers = useMemo(() => {
    if (!response?.players) return [];
    return response.players;
  }, [response]);

  // Build player_key -> player lookup
  const playerMap = useMemo(() => {
    const map = new Map<string, PlayerDatabaseEntry>();
    for (const p of allPlayers) {
      if (p.yahoo_player_id) map.set(p.yahoo_player_id, p);
    }
    return map;
  }, [allPlayers]);

  // Initialize custom order from localStorage or o_rank
  useEffect(() => {
    if (!allPlayers.length || !selectedYear) return;

    const saved = loadCustomOrder(selectedYear);
    if (saved) {
      // Merge: add new players not in saved order
      const savedSet = new Set(saved);
      const newKeys = allPlayers
        .filter((p) => p.yahoo_player_id && !savedSet.has(p.yahoo_player_id))
        .sort((a, b) => (a.o_rank ?? 9999) - (b.o_rank ?? 9999))
        .map((p) => p.yahoo_player_id);
      // Remove keys no longer in data
      const dataKeys = new Set(allPlayers.map((p) => p.yahoo_player_id));
      const cleaned = saved.filter((k) => dataKeys.has(k));
      setCustomOrder([...cleaned, ...newKeys]);
    } else {
      // Default: o_rank order
      const ordered = [...allPlayers]
        .sort((a, b) => (a.o_rank ?? 9999) - (b.o_rank ?? 9999))
        .map((p) => p.yahoo_player_id)
        .filter(Boolean);
      setCustomOrder(ordered);
    }
  }, [allPlayers, selectedYear]);

  // Debounced save to localStorage
  const persistOrder = useCallback(
    (order: string[]) => {
      if (!selectedYear) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        saveCustomOrder(selectedYear, order);
      }, 1500);
    },
    [selectedYear],
  );

  // Full ordered player list (before filtering)
  const orderedPlayers = useMemo(() => {
    if (!customOrder) return allPlayers;
    const result: PlayerDatabaseEntry[] = [];
    for (const key of customOrder) {
      const p = playerMap.get(key);
      if (p) result.push(p);
    }
    return result;
  }, [customOrder, playerMap, allPlayers]);

  // Filtered list for display
  const filteredPlayers = useMemo(() => {
    let list = orderedPlayers;

    // Position filter
    if (positionFilter === "BATTER") {
      list = list.filter((p) => isBatter(p.position));
    } else if (positionFilter === "PITCHER") {
      list = list.filter((p) => isPitcher(p.position));
    } else if (positionFilter !== "ALL") {
      const target = positionFilter.toUpperCase();
      const groupMap: Record<string, Set<string>> = {
        OF: new Set(["LF", "CF", "RF", "OF"]),
      };
      const matchSet = groupMap[target] ?? new Set([target]);
      list = list.filter((p) => {
        const parts = (p.position || "").split(",").map((s) => s.trim().toUpperCase());
        return parts.some((pp) => matchSet.has(pp));
      });
    }

    // Search filter
    if (committedSearch.trim()) {
      const q = committedSearch.trim().toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.mlb_team.toLowerCase().includes(q),
      );
    }

    return list;
  }, [orderedPlayers, positionFilter, committedSearch]);

  // ── Reorder helpers ──
  function movePlayer(fromIdx: number, toIdx: number) {
    if (!customOrder) return;
    // fromIdx/toIdx are in filtered view — need to map to customOrder indices
    const fromPlayer = filteredPlayers[fromIdx];
    const toPlayer = filteredPlayers[toIdx];
    if (!fromPlayer || !toPlayer) return;

    const fromKey = fromPlayer.yahoo_player_id;
    const toKey = toPlayer.yahoo_player_id;

    const newOrder = [...customOrder];
    const fromOrderIdx = newOrder.indexOf(fromKey);
    const toOrderIdx = newOrder.indexOf(toKey);
    if (fromOrderIdx === -1 || toOrderIdx === -1) return;

    // Remove and insert
    newOrder.splice(fromOrderIdx, 1);
    newOrder.splice(toOrderIdx, 0, fromKey);

    setCustomOrder(newOrder);
    persistOrder(newOrder);
  }

  function jumpToRank(playerKey: string, targetRank: number) {
    if (!customOrder) return;
    const idx = customOrder.indexOf(playerKey);
    if (idx === -1) return;

    const newOrder = [...customOrder];
    newOrder.splice(idx, 1);
    const insertAt = Math.max(0, Math.min(targetRank - 1, newOrder.length));
    newOrder.splice(insertAt, 0, playerKey);

    setCustomOrder(newOrder);
    persistOrder(newOrder);
    setJumpTarget(null);
  }

  function resetRankings() {
    if (!selectedYear || !allPlayers.length) return;
    const ordered = [...allPlayers]
      .sort((a, b) => (a.o_rank ?? 9999) - (b.o_rank ?? 9999))
      .map((p) => p.yahoo_player_id)
      .filter(Boolean);
    setCustomOrder(ordered);
    localStorage.removeItem(STORAGE_KEY(selectedYear));
  }

  // ── Drag handlers ──
  function handleDragStart(idx: number) {
    setDragIdx(idx);
  }
  function handleDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    setDragOverIdx(idx);
  }
  function handleDrop(idx: number) {
    if (dragIdx !== null && dragIdx !== idx) {
      movePlayer(dragIdx, idx);
    }
    setDragIdx(null);
    setDragOverIdx(null);
  }
  function handleDragEnd() {
    setDragIdx(null);
    setDragOverIdx(null);
  }

  // Auto-adjust stat column visibility by position filter
  useEffect(() => {
    if (positionFilter === "PITCHER") {
      setShowHitting(false);
      setShowPitching(true);
    } else if (positionFilter === "BATTER") {
      setShowHitting(true);
      setShowPitching(false);
    }
  }, [positionFilter]);

  // Helper: get custom rank (1-indexed in full order)
  function getCustomRank(playerKey: string): number {
    if (!customOrder) return 0;
    return customOrder.indexOf(playerKey) + 1;
  }

  const isFiltered = positionFilter !== "ALL" || committedSearch.trim() !== "";

  return (
    <div className="mx-auto max-w-[1400px] px-2 py-4 sm:px-4 sm:py-6">
      <div className="mb-4 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
            選秀策略 Draft Strategy
          </h1>
          <p className="mt-1 text-xs text-gray-500 sm:text-sm">
            根據 Yahoo Fantasy 排名，拖曳或使用箭頭建立你的自訂選秀順位
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Year selector */}
          <select
            value={selectedYear}
            onChange={(e) => {
              setSelectedYear(Number(e.target.value));
              setCustomOrder(null);
            }}
            className="rounded border border-gray-300 bg-white px-2 py-1.5 text-sm"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>

          {/* Reset button */}
          <button
            onClick={resetRankings}
            className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            重設排名
          </button>
        </div>
      </div>

      {/* Position filter + search */}
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
        {/* Position pills */}
        <div className="flex flex-wrap gap-1.5 sm:gap-1">
          {POSITION_GROUPS.map((pos) => (
            <button
              key={pos}
              onClick={() => {
                setPositionFilter(pos);
              }}
              className={`min-h-[36px] min-w-[36px] rounded-full px-3 py-1.5 text-xs font-medium transition sm:min-h-0 sm:min-w-0 sm:px-2.5 sm:py-1 ${
                positionFilter === pos
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {pos}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative flex-1 sm:max-w-xs">
          <input
            type="text"
            placeholder="搜尋球員 / MLB 球隊..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setCommittedSearch(searchQuery);
            }}
            className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
          {committedSearch && (
            <button
              onClick={() => {
                setSearchQuery("");
                setCommittedSearch("");
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              x
            </button>
          )}
        </div>

        {/* Stat column toggles - only visible on md+ where stats are shown */}
        <div className="hidden items-center gap-2 text-xs md:flex">
          <button
            onClick={() => setShowHitting(!showHitting)}
            className={`rounded px-2 py-1 ${
              showHitting
                ? "bg-blue-100 text-blue-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            打擊
          </button>
          <button
            onClick={() => setShowPitching(!showPitching)}
            className={`rounded px-2 py-1 ${
              showPitching
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            投球
          </button>
        </div>
      </div>

      {/* Info bar */}
      <div className="mb-2 flex items-center gap-3 text-xs text-gray-500">
        <span>
          共 {filteredPlayers.length} 位球員
          {isFiltered && ` (全部 ${orderedPlayers.length})`}
        </span>
        {isFiltered && (
          <span className="text-amber-600">
            篩選模式 - 排序操作只在篩選結果內移動
          </span>
        )}
        {customOrder && loadCustomOrder(selectedYear) && (
          <span className="text-emerald-600">
            已載入自訂排名
          </span>
        )}
      </div>

      {/* Main table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-xs">
            <thead className="bg-gray-50">
              <tr className="border-b text-left text-gray-500">
                <th className="w-10 px-2 py-2 text-center">#</th>
                <th className="hidden w-14 px-2 py-2 text-center sm:table-cell">Yahoo</th>
                <th className="min-w-[120px] px-2 py-2 sm:min-w-[140px]">球員</th>
                <th className="w-14 px-2 py-2 sm:w-16">位置</th>
                <th className="hidden px-2 py-2 sm:table-cell sm:w-14">MLB</th>
                <th className="hidden px-2 py-2 sm:table-cell sm:w-12">狀態</th>
                {showHitting &&
                  HITTING_COLS.map((c) => (
                    <th key={c.key} className="hidden w-10 px-1 py-2 text-right md:table-cell">
                      {c.label}
                    </th>
                  ))}
                {showPitching &&
                  PITCHING_COLS.map((c) => (
                    <th key={c.key} className="hidden w-10 px-1 py-2 text-right md:table-cell">
                      {c.label}
                    </th>
                  ))}
                <th className="w-20 px-2 py-2 text-center">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredPlayers.map((p, idx) => {
                const customRank = getCustomRank(p.yahoo_player_id);
                const yahooRank = p.o_rank;
                const isDragging = dragIdx === idx;
                const isDragOver = dragOverIdx === idx;
                const stats = p.stats || {};
                const isJumping =
                  jumpTarget?.playerKey === p.yahoo_player_id;

                return (
                  <tr
                    key={p.yahoo_player_id || `${p.name}-${idx}`}
                    draggable
                    onDragStart={() => handleDragStart(idx)}
                    onDragOver={(e) => handleDragOver(e, idx)}
                    onDrop={() => handleDrop(idx)}
                    onDragEnd={handleDragEnd}
                    className={`border-b transition-colors ${
                      isDragging
                        ? "opacity-40"
                        : isDragOver
                          ? "bg-indigo-50 border-indigo-300"
                          : "hover:bg-gray-50"
                    } cursor-grab active:cursor-grabbing`}
                  >
                    {/* Custom rank */}
                    <td className="px-2 py-1.5 text-center font-mono font-bold text-gray-700">
                      {isJumping ? (
                        <input
                          type="number"
                          autoFocus
                          value={jumpTarget.value}
                          onChange={(e) =>
                            setJumpTarget({
                              playerKey: p.yahoo_player_id,
                              value: e.target.value,
                            })
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const n = parseInt(jumpTarget.value);
                              if (n > 0) jumpToRank(p.yahoo_player_id, n);
                            }
                            if (e.key === "Escape") setJumpTarget(null);
                          }}
                          onBlur={() => setJumpTarget(null)}
                          className="w-12 rounded border border-indigo-400 px-1 py-0.5 text-center text-xs"
                          min={1}
                        />
                      ) : (
                        <button
                          onClick={() =>
                            setJumpTarget({
                              playerKey: p.yahoo_player_id,
                              value: String(customRank),
                            })
                          }
                          className="hover:text-indigo-600"
                          title="點擊輸入目標排名"
                        >
                          {customRank}
                        </button>
                      )}
                    </td>

                    {/* Yahoo rank - hidden on mobile */}
                    <td className="hidden px-2 py-1.5 text-center text-gray-400 sm:table-cell">
                      {yahooRank ?? "-"}
                    </td>

                    {/* Player name */}
                    <td className="px-2 py-1.5 font-medium">
                      <span className="inline-flex items-center gap-1">
                        <button
                          onClick={() =>
                            setModalPlayer({
                              name: p.name,
                              position: p.position,
                            })
                          }
                          className="text-left text-indigo-600 hover:text-indigo-800 hover:underline"
                        >
                          {p.name}
                        </button>
                        <StatusBadge status={p.status} />
                      </span>
                    </td>

                    {/* Position */}
                    <td className="px-2 py-1.5 text-gray-600">{p.position}</td>

                    {/* MLB team - hidden on mobile */}
                    <td className="hidden px-2 py-1.5 text-gray-600 sm:table-cell">{p.mlb_team}</td>

                    {/* Status - hidden on mobile (shown inline with name) */}
                    <td className="hidden px-2 py-1.5 sm:table-cell">
                      <StatusBadge status={p.status} />
                    </td>

                    {/* Hitting stats - hidden on mobile */}
                    {showHitting &&
                      HITTING_COLS.map((c) => (
                        <td
                          key={c.key}
                          className="hidden px-1 py-1.5 text-right tabular-nums text-gray-600 md:table-cell"
                        >
                          {formatStat(
                            stats[c.key as keyof typeof stats] as
                              | number
                              | undefined,
                            c.key,
                          )}
                        </td>
                      ))}

                    {/* Pitching stats - hidden on mobile */}
                    {showPitching &&
                      PITCHING_COLS.map((c) => (
                        <td
                          key={c.key}
                          className="hidden px-1 py-1.5 text-right tabular-nums text-gray-600 md:table-cell"
                        >
                          {formatStat(
                            stats[c.key as keyof typeof stats] as
                              | number
                              | undefined,
                            c.key,
                          )}
                        </td>
                      ))}

                    {/* Actions: up/down arrows (touch-friendly) */}
                    <td className="px-1 py-1 text-center sm:px-2 sm:py-1.5">
                      <div className="inline-flex gap-0.5">
                        <button
                          onClick={() => {
                            if (idx > 0) movePlayer(idx, idx - 1);
                          }}
                          disabled={idx === 0}
                          className="min-h-[44px] min-w-[44px] rounded p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 sm:min-h-0 sm:min-w-0 sm:p-0.5"
                          title="上移"
                        >
                          <svg
                            className="mx-auto h-5 w-5 sm:h-4 sm:w-4"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M5 15l7-7 7 7"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={() => {
                            if (idx < filteredPlayers.length - 1)
                              movePlayer(idx, idx + 1);
                          }}
                          disabled={idx === filteredPlayers.length - 1}
                          className="min-h-[44px] min-w-[44px] rounded p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 sm:min-h-0 sm:min-w-0 sm:p-0.5"
                          title="下移"
                        >
                          <svg
                            className="mx-auto h-5 w-5 sm:h-4 sm:w-4"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M19 9l-7 7-7-7"
                            />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filteredPlayers.length === 0 && (
                <tr>
                  <td
                    colSpan={99}
                    className="px-4 py-12 text-center text-gray-400"
                  >
                    {isLoading
                      ? "載入中..."
                      : committedSearch
                        ? `找不到「${committedSearch}」相關球員`
                        : "尚無排名資料，請至球員頁面由 Commissioner 獲取排名"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Hint */}
      <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
        <ul className="list-inside list-disc space-y-0.5">
          <li className="hidden sm:list-item">拖曳表格列可移動球員排名順位（桌面版）</li>
          <li>
            點擊排名數字可直接輸入目標排名，按 Enter 確認
          </li>
          <li>使用右側箭頭按鈕微調順位</li>
          <li>自訂排名會自動儲存在瀏覽器中（localStorage）</li>
          <li>
            球員狀態：
            <span className="ml-1 inline-flex items-center gap-1">
              <StatusBadge status="IL" /> 傷兵名單
              <StatusBadge status="IL+" /> 60 天傷兵
              <StatusBadge status="DTD" /> Day-to-Day
              <StatusBadge status="NA" /> 非 40 人名單
            </span>
          </li>
        </ul>
      </div>

      {/* Player stats modal */}
      {modalPlayer && (
        <PlayerStatsModal
          playerName={modalPlayer.name}
          position={modalPlayer.position}
          onClose={() => setModalPlayer(null)}
        />
      )}
    </div>
  );
}
