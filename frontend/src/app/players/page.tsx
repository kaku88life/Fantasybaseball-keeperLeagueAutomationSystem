"use client";

import { useCallback, useEffect, useState } from "react";
import useSWR from "swr";
import {
  getPlayerDatabase,
  getYears,
  fetchYahooRankings,
  getRankingFetchStatus,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ContractBadge from "@/components/ContractBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import PlayerStatsModal from "@/components/PlayerStatsModal";
import { POSITION_GROUPS } from "@/components/PositionFilter";
import type {
  ContractType,
  PlayerDatabaseEntry,
  PlayerDatabaseResponse,
  RankingFetchStatus,
} from "@/types";

// MLB team list (30 teams)
const MLB_TEAMS = [
  "ARI", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE",
  "COL", "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL",
  "MIN", "NYM", "NYY", "OAK", "PHI", "PIT", "SD", "SF",
  "SEA", "STL", "TB", "TEX", "TOR", "WAS",
];

// Sort type options for Yahoo API stats fetch
// Combines year context + time range into a single dropdown
const SORT_TYPE_OPTIONS = [
  { label: "2026 \u6574\u5b63", value: "season" },
  { label: "2026 \u8fd1\u4e00\u9031", value: "lastweek" },
  { label: "2026 \u8fd1\u4e00\u6708", value: "lastmonth" },
  { label: "2026 \u4eca\u65e5", value: "date" },
  { label: "2025 \u6574\u5b63", value: "prev_season" },
] as const;

// Rows per page
const ROWS_PER_PAGE = 200;

// Sort key type (POS, MLB, owner removed — now filter-only)
type SortKey =
  | "o_rank" | "ar_rank" | "name"
  | "salary"
  | "ab" | "r" | "h" | "hr" | "rbi" | "sb" | "avg" | "ops"
  | "ip" | "w" | "sv" | "hld" | "k" | "era" | "whip" | "qs";

interface SortState {
  key: SortKey;
  dir: "asc" | "desc";
}

// Stat columns config
const HITTING_COLS: Array<{ key: string; label: string }> = [
  { key: "ab", label: "AB" },
  { key: "r", label: "R" },
  { key: "h", label: "H" },
  { key: "hr", label: "HR" },
  { key: "rbi", label: "RBI" },
  { key: "sb", label: "SB" },
  { key: "avg", label: "AVG" },
  { key: "ops", label: "OPS" },
];

const PITCHING_COLS: Array<{ key: string; label: string }> = [
  { key: "ip", label: "IP" },
  { key: "w", label: "W" },
  { key: "sv", label: "SV" },
  { key: "hld", label: "HLD" },
  { key: "k", label: "K" },
  { key: "era", label: "ERA" },
  { key: "whip", label: "WHIP" },
  { key: "qs", label: "QS" },
];

function isPitcher(position: string): boolean {
  const pos = position.split(",").map((s) => s.trim().toUpperCase());
  return pos.some((p) => ["SP", "RP", "P"].includes(p));
}

export default function PlayersPage() {
  const { user } = useAuth();
  const isCommissioner = user?.is_commissioner ?? false;

  // SWR cached data
  const { data: years = [] } = useSWR("years", getYears);
  const [selectedYear, setSelectedYear] = useState<number>(0);
  const effectiveYear = selectedYear || (years.length > 0 ? Math.max(...years) : new Date().getFullYear());

  // Filters (sent to server)
  const [positionFilter, setPositionFilter] = useState("ALL");
  const [mlbTeamFilter, setMlbTeamFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  // Search triggers on Enter key press
  const [committedSearch, setCommittedSearch] = useState("");

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);

  // Sort
  const [sort, setSort] = useState<SortState>({ key: "o_rank", dir: "asc" });

  // Map owner filter: __FA__ -> contract=fa, else owner=name
  const serverOwner = ownerFilter === "__FA__" ? "" : ownerFilter;
  const serverContract = ownerFilter === "__FA__" ? "fa" : "";

  // Map position filter: BATTER/PITCHER -> player_type, others -> position
  const isBatterPitcher = positionFilter === "BATTER" || positionFilter === "PITCHER";
  const serverPosition = isBatterPitcher || positionFilter === "ALL" ? "" : positionFilter;
  const serverPlayerType = positionFilter === "BATTER" ? "batter" : positionFilter === "PITCHER" ? "pitcher" : "";

  // SWR data fetch with server-side filtering/pagination
  const swrKey = effectiveYear
    ? JSON.stringify({
        ep: `player-db-${effectiveYear}`,
        page: currentPage,
        search: committedSearch,
        position: serverPosition,
        player_type: serverPlayerType,
        mlb_team: mlbTeamFilter,
        owner: serverOwner,
        contract: serverContract,
        sort_key: sort.key,
        sort_dir: sort.dir,
      })
    : null;
  const { data, error: dataErr, isLoading: loading, mutate: mutatePlayerData } = useSWR(
    swrKey,
    () =>
      getPlayerDatabase(effectiveYear, {
        page: currentPage,
        page_size: ROWS_PER_PAGE,
        search: committedSearch,
        position: serverPosition,
        player_type: serverPlayerType,
        mlb_team: mlbTeamFilter,
        owner: serverOwner,
        contract: serverContract,
        sort_key: sort.key,
        sort_dir: sort.dir,
      }),
    { keepPreviousData: true },
  );
  const error = dataErr?.message || "";

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [positionFilter, mlbTeamFilter, ownerFilter, committedSearch, sort]);

  // Player stats modal
  const [modalPlayer, setModalPlayer] = useState<{ name: string; position: string } | null>(null);

  // Info guide toggle
  const [showGuide, setShowGuide] = useState(false);

  // Sort type for Yahoo rankings (controls stat time range)
  const [sortType, setSortType] = useState("season");

  // Commissioner ranking fetch
  const { data: rankingStatus, mutate: mutateRankingStatus } = useSWR(
    isCommissioner && effectiveYear ? `ranking-status-${effectiveYear}` : null,
    () => getRankingFetchStatus(effectiveYear),
  );
  const [fetching, setFetching] = useState(false);
  const [fetchMessage, setFetchMessage] = useState("");

  // Handle ranking fetch
  const handleFetchRankings = useCallback(async () => {
    setFetching(true);
    setFetchMessage("");
    try {
      const result = await fetchYahooRankings(effectiveYear, sortType);
      setFetchMessage(result.message);
      // Revalidate cached data
      mutatePlayerData();
      mutateRankingStatus();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Fetch failed";
      setFetchMessage(`Error: ${msg}`);
    } finally {
      setFetching(false);
    }
  }, [effectiveYear, sortType, mutatePlayerData, mutateRankingStatus]);

  // Sort handler
  const handleSort = useCallback(
    (key: SortKey) => {
      setSort((prev) =>
        prev.key === key
          ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
          : { key, dir: "asc" },
      );
    },
    [],
  );

  // Server provides owner list and pagination
  const ownerList = data?.owners ?? [];
  const totalPages = data?.total_pages ?? 1;
  const paginatedPlayers = data?.players ?? [];

  // Sort arrow indicator
  const SortArrow = ({ col }: { col: SortKey }) => {
    if (sort.key !== col) return <span className="ml-0.5 text-gray-300">&#x25B2;</span>;
    return (
      <span className="ml-0.5 text-indigo-600">
        {sort.dir === "asc" ? "\u25B2" : "\u25BC"}
      </span>
    );
  };

  // Sortable table header
  const SortTh = ({
    col,
    label,
    className = "",
  }: {
    col: SortKey;
    label: string;
    className?: string;
  }) => (
    <th
      className={`cursor-pointer select-none whitespace-nowrap px-2 py-2 text-left text-xs font-medium uppercase text-gray-500 hover:text-gray-700 ${className}`}
      onClick={() => handleSort(col)}
    >
      {label}
      <SortArrow col={col} />
    </th>
  );

  // Format stat value for display
  const formatStat = (val: number | undefined, key: string): string => {
    if (val === undefined || val === null) return "-";
    if (key === "avg" || key === "ops") return val.toFixed(3);
    if (key === "era") return val.toFixed(2);
    if (key === "whip") return val.toFixed(2);
    return String(val);
  };

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="rounded-lg bg-red-50 p-4 text-red-800">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[100rem] px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          球員資料庫 Player Database
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {data?.total_count ?? 0} 位球員
          {data?.has_rankings && " (含 Yahoo 排名)"}
        </p>
      </div>

      {/* Info Guide (collapsible) */}
      <div className="mb-4">
        <button
          onClick={() => setShowGuide((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100"
        >
          <span className={`inline-block transition-transform ${showGuide ? "rotate-90" : ""}`}>
            &#9654;
          </span>
          資料說明 Info Guide
        </button>

        {showGuide && (
          <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-gray-700">
            <div className="grid gap-4 md:grid-cols-3">
              {/* Data Sources */}
              <div>
                <h3 className="mb-2 font-semibold text-blue-800">
                  資料來源 Data Source
                </h3>
                <ul className="space-y-1 text-xs">
                  <li>
                    <span className="font-medium">OR</span> (Overall Rank)
                    {" "}= Yahoo 預季預測排名
                  </li>
                  <li>
                    <span className="font-medium">AR</span> (Actual Rank)
                    {" "}= Yahoo 當季實際表現排名
                  </li>
                  <li>
                    <span className="font-medium">成績欄位</span>
                    {" "}= 由右方下拉選單控制數據來源
                  </li>
                </ul>
                <h4 className="mb-1 mt-2 text-xs font-medium text-blue-700">
                  成績時間範圍
                </h4>
                <ul className="space-y-0.5 text-xs text-gray-600">
                  <li>2026 整季 = 2026 全季累計成績</li>
                  <li>2026 近一週 / 近一月 / 今日 = 近期表現</li>
                  <li>2025 整季 = 上季完整成績</li>
                </ul>
              </div>

              {/* Column Guide */}
              <div>
                <h3 className="mb-2 font-semibold text-blue-800">
                  欄位說明 Column Guide
                </h3>
                <ul className="space-y-1 text-xs">
                  <li>
                    <span className="font-medium">2025</span>
                    {" "}= 當前合約狀態 (A/B/N/O/R)
                  </li>
                  <li>
                    <span className="font-medium">2026</span>
                    {" "}= 下一年合約狀態
                    <span className="text-gray-500">
                      （已繳交隊伍顯示實際選擇，未繳交顯示「待定」）
                    </span>
                  </li>
                  <li>
                    <span className="font-medium">$</span>
                    {" "}= 球員薪資
                  </li>
                  <li>
                    <span className="font-medium">歸屬</span>
                    {" "}= 球員所屬經理，FA 為自由球員
                  </li>
                </ul>
              </div>

              {/* Notes */}
              <div>
                <h3 className="mb-2 font-semibold text-blue-800">
                  注意事項 Notes
                </h3>
                <ul className="space-y-1 text-xs">
                  <li>
                    所有排名與數據<span className="font-medium">以 Yahoo Fantasy 系統為準</span>，本頁僅供參考
                  </li>
                  <li>
                    部分球員可能未被 Yahoo 收錄排名，OR/AR 將顯示「-」
                  </li>
                  <li>
                    切換成績時間範圍後，需由 Commissioner 重新擷取排名才會更新數據
                  </li>
                  <li>
                    搜尋功能請輸入後按 <kbd className="rounded border border-gray-300 bg-white px-1 py-0.5 font-mono text-[10px]">Enter</kbd> 鍵送出
                  </li>
                  <li>
                    點擊球員名字可查看 MLB 歷年成績
                  </li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Controls Row */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {/* Year dropdown */}
          <select
            value={effectiveYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>

          {/* Position dropdown */}
          <select
            value={positionFilter}
            onChange={(e) => setPositionFilter(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            {POSITION_GROUPS.map((pg) => (
              <option key={pg.value} value={pg.value}>
                {pg.value === "ALL" ? "All Positions" : pg.label}
              </option>
            ))}
          </select>

          {/* MLB Team dropdown */}
          <select
            value={mlbTeamFilter}
            onChange={(e) => setMlbTeamFilter(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option value="">All Teams</option>
            {MLB_TEAMS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          {/* Owner dropdown */}
          <select
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option value="">All Owners</option>
            <option value="__FA__">FA (Free Agent)</option>
            {ownerList.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>

          {/* Sort Type dropdown (stat time range for Yahoo rankings) */}
          <select
            value={sortType}
            onChange={(e) => setSortType(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            title="Stats time range (used when fetching Yahoo rankings)"
          >
            {SORT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {/* Search (Enter to submit) */}
          <input
            type="text"
            placeholder="搜尋球員或經理 (Enter)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setCommittedSearch(searchQuery);
              }
            }}
            className="w-48 rounded-md border border-gray-300 px-3 py-1.5 text-sm placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>

      </div>

      {/* Commissioner: Fetch Rankings */}
      {isCommissioner && (
        <div className="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 p-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded bg-yellow-600 px-2 py-0.5 text-xs font-semibold text-white">
              CM
            </span>
            <button
              onClick={handleFetchRankings}
              disabled={fetching}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {fetching ? "擷取中..." : "擷取 Yahoo 排名"}
            </button>
            {rankingStatus && (
              <span className="text-xs text-gray-600">
                {rankingStatus.has_data
                  ? `${rankingStatus.total_count} 筆 | 上次更新: ${new Date(rankingStatus.last_fetched_at!).toLocaleString("zh-TW")}`
                  : "尚未擷取排名資料"}
              </span>
            )}
            {fetchMessage && (
              <span
                className={`text-xs ${fetchMessage.startsWith("Error") ? "text-red-600" : "text-green-600"}`}
              >
                {fetchMessage}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Result count + pagination info */}
      <div className="mb-2 flex items-center justify-between text-sm text-gray-500">
        <span>
          篩選結果 {data?.total_count ?? 0} 位球員
          {totalPages > 1 && (
            <span className="ml-2">
              (第 {currentPage}/{totalPages} 頁，顯示 {paginatedPlayers.length} 筆)
            </span>
          )}
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <SortTh col="o_rank" label="OR" className="w-10" />
              <SortTh col="ar_rank" label="AR" className="w-10" />
              <SortTh col="name" label="球員" />
              <th className="whitespace-nowrap px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                Pos
              </th>
              <th className="whitespace-nowrap px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                MLB
              </th>
              <th className="px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                2025
              </th>
              <th className="px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                2026
              </th>
              <SortTh col="salary" label="$" />
              <th className="whitespace-nowrap px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                歸屬
              </th>

              {/* Stats columns */}
              {HITTING_COLS.map((c) => (
                <SortTh
                  key={c.key}
                  col={c.key as SortKey}
                  label={c.label}
                  className=""
                />
              ))}
              {PITCHING_COLS.map((c) => (
                <SortTh
                  key={c.key}
                  col={c.key as SortKey}
                  label={c.label}
                  className=""
                />
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {paginatedPlayers.map((p, idx) => {
              const pitcher = isPitcher(p.position);
              const statSource = p.stats;

              return (
                <tr
                  key={`${p.yahoo_player_id || p.name}-${idx}`}
                  className="hover:bg-gray-50"
                >
                  {/* OR (Overall Rank) */}
                  <td className="whitespace-nowrap px-2 py-1.5 text-gray-400">
                    {p.o_rank ?? "-"}
                  </td>

                  {/* AR (Actual Rank) */}
                  <td className="whitespace-nowrap px-2 py-1.5 text-xs text-gray-500">
                    {p.ar_rank ?? "-"}
                  </td>

                  {/* Player name */}
                  <td className="whitespace-nowrap px-2 py-1.5 font-medium">
                    <button
                      onClick={() =>
                        setModalPlayer({ name: p.name, position: p.position })
                      }
                      className="text-left text-indigo-600 hover:text-indigo-800 hover:underline"
                    >
                      {p.name}
                    </button>
                  </td>

                  {/* Position */}
                  <td className="whitespace-nowrap px-2 py-1.5 text-xs text-gray-600">
                    {p.position}
                  </td>

                  {/* MLB Team */}
                  <td className="whitespace-nowrap px-2 py-1.5 text-xs text-gray-500">
                    {p.mlb_team || "-"}
                  </td>

                  {/* 2025 Contract */}
                  <td className="whitespace-nowrap px-2 py-1.5">
                    {p.contract_display ? (
                      <ContractBadge
                        type={p.contract_type as ContractType}
                        display={p.contract_display}
                      />
                    ) : (
                      <span className="text-xs text-gray-300">FA</span>
                    )}
                  </td>

                  {/* 2026 Status */}
                  <td className="whitespace-nowrap px-2 py-1.5">
                    {p.next_contract_display ? (
                      <ContractBadge
                        type={p.next_contract_type as ContractType}
                        display={p.next_contract_display}
                      />
                    ) : (
                      <span className="text-xs text-gray-300">-</span>
                    )}
                  </td>

                  {/* Salary */}
                  <td className="whitespace-nowrap px-2 py-1.5 text-right text-xs">
                    {p.salary > 0 ? `$${p.salary}` : "-"}
                  </td>

                  {/* Owner */}
                  <td className="whitespace-nowrap px-2 py-1.5 text-xs text-gray-600">
                    {p.owner_manager || (
                      <span className="text-gray-300">FA</span>
                    )}
                  </td>

                  {/* Hitting stats */}
                  {HITTING_COLS.map((c) => (
                    <td
                      key={c.key}
                      className={`whitespace-nowrap px-2 py-1.5 text-right text-xs ${
                        pitcher ? "text-gray-300" : "text-gray-700"
                      }`}
                    >
                      {!pitcher
                        ? formatStat(
                            statSource[c.key as keyof typeof statSource] as
                              | number
                              | undefined,
                            c.key,
                          )
                        : "-"}
                    </td>
                  ))}

                  {/* Pitching stats */}
                  {PITCHING_COLS.map((c) => (
                    <td
                      key={c.key}
                      className={`whitespace-nowrap px-2 py-1.5 text-right text-xs ${
                        !pitcher ? "text-gray-300" : "text-gray-700"
                      }`}
                    >
                      {pitcher
                        ? formatStat(
                            statSource[c.key as keyof typeof statSource] as
                              | number
                              | undefined,
                            c.key,
                          )
                        : "-"}
                    </td>
                  ))}
                </tr>
              );
            })}

            {paginatedPlayers.length === 0 && (
              <tr>
                <td
                  colSpan={9 + HITTING_COLS.length + PITCHING_COLS.length}
                  className="py-8 text-center text-gray-400"
                >
                  沒有符合條件的球員
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            onClick={() => setCurrentPage(1)}
            disabled={currentPage === 1}
            className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40"
          >
            &laquo;
          </button>
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
          >
            上一頁
          </button>

          {/* Page numbers */}
          {Array.from({ length: totalPages }, (_, i) => i + 1)
            .filter((p) => {
              // Show: first, last, and pages near current
              if (p === 1 || p === totalPages) return true;
              if (Math.abs(p - currentPage) <= 2) return true;
              return false;
            })
            .reduce<(number | "...")[]>((acc, p, i, arr) => {
              if (i > 0 && p - (arr[i - 1] as number) > 1) acc.push("...");
              acc.push(p);
              return acc;
            }, [])
            .map((item, i) =>
              item === "..." ? (
                <span key={`ellipsis-${i}`} className="px-1 text-gray-400">
                  ...
                </span>
              ) : (
                <button
                  key={item}
                  onClick={() => setCurrentPage(item as number)}
                  className={`rounded border px-3 py-1 text-sm ${
                    currentPage === item
                      ? "border-indigo-500 bg-indigo-600 text-white"
                      : "border-gray-300 text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  {item}
                </button>
              ),
            )}

          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
          >
            下一頁
          </button>
          <button
            onClick={() => setCurrentPage(totalPages)}
            disabled={currentPage === totalPages}
            className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-40"
          >
            &raquo;
          </button>
        </div>
      )}

      {/* Player Stats Modal */}
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
