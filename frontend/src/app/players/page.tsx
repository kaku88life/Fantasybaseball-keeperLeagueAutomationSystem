"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import {
  getPlayerDatabase,
  getYears,
  fetchYahooRankings,
  getRankingFetchStatus,
  getProspects,
  reloadProspects,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ContractBadge from "@/components/ContractBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import StatusBadge from "@/components/StatusBadge";
import PlayerStatsModal from "@/components/PlayerStatsModal";
import { POSITION_GROUPS } from "@/components/PositionFilter";
import type {
  ContractType,
  PlayerDatabaseEntry,
  PlayerDatabaseResponse,
  ProspectEntry,
  ProspectsResponse,
  RankingFetchStatus,
} from "@/types";

// Tab definitions
const TABS = [
  { id: "database", label: "球員資料庫" },
  { id: "prospects", label: "百大新秀" },
] as const;
type TabId = (typeof TABS)[number]["id"];

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
  { label: "2026 整季", value: "season" },
  { label: "2026 近一週", value: "lastweek" },
  { label: "2026 近一月", value: "lastmonth" },
  { label: "2026 今日", value: "date" },
  { label: "2025 整季", value: "prev_season" },
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

// Stat columns config (shared)
import {
  ADV_BATTING_COLS,
  ADV_PITCHING_COLS,
  BUY_SIGNAL_MILD,
  BUY_SIGNAL_STRONG,
  HITTING_COLS,
  PITCHING_COLS,
  buySignalGap,
  buySignalLevel,
  formatAdvStat,
  formatStat,
} from "@/lib/stats";
import { metricTooltip, type MetricKey } from "@/lib/statcastGlossary";
import { lookupStatcast } from "@/lib/api";
import type { StatcastLookupResponse } from "@/types";

// Prospect ownership filter options
const PROSPECT_OWNER_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "owned", label: "已持有" },
  { value: "fa", label: "FA" },
] as const;

import { isPitcher } from "@/lib/position";

export default function PlayersPage() {
  const { user } = useAuth();
  const isCommissioner = user?.is_commissioner ?? false;
  const isAuth = !!user;

  // Tab state
  const [activeTab, setActiveTab] = useState<TabId>("database");

  // SWR cached data
  const { data: allYears = [] } = useSWR("years", getYears);
  // Player Database only supports up to current season; hide future projections (e.g. 2027)
  const years = useMemo(() => allYears.filter((y) => y <= 2026), [allYears]);
  const [selectedYear, setSelectedYear] = useState<number>(0);
  const effectiveYear = selectedYear || (years.length > 0 ? Math.max(...years) : new Date().getFullYear());

  // ============================================================
  // Database tab state
  // ============================================================
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

  // Stats column visibility (collapsible)
  const [showHitting, setShowHitting] = useState(true);
  const [showPitching, setShowPitching] = useState(true);

  // Statcast columns are opt-in: they cost an extra request and widen the table.
  const [showAdvanced, setShowAdvanced] = useState(false);
  // "season" shows the season aggregate the lookup already returns; numbers are
  // rolling windows in days (backend accepts 3-60).
  const [advWindow, setAdvWindow] = useState<number | "season">(15);
  const [advData, setAdvData] = useState<StatcastLookupResponse | null>(null);
  const [advLoading, setAdvLoading] = useState(false);
  const [advError, setAdvError] = useState("");

  // Auto-toggle based on position filter
  const effectiveShowHitting = positionFilter === "PITCHER" ? false : showHitting;
  const effectiveShowPitching = positionFilter === "BATTER" ? false : showPitching;

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

  // Player stats modal (shared between tabs)
  const [modalPlayer, setModalPlayer] = useState<{ name: string; position: string } | null>(null);

  // Info guide toggle
  const [showGuide, setShowGuide] = useState(false);

  // Sort type for Yahoo rankings (controls stat time range)
  // Defaults to "prev_season" (2025 stats) — synced from API response when data loads
  const [sortType, setSortType] = useState("prev_season");
  const [sortTypeInitialized, setSortTypeInitialized] = useState(false);

  // Sync sortType dropdown with stored stats_sort_type on first data load
  useEffect(() => {
    if (!sortTypeInitialized && data?.stats_sort_type) {
      setSortType(data.stats_sort_type);
      setSortTypeInitialized(true);
    }
  }, [data?.stats_sort_type, sortTypeInitialized]);

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

  // Fetch Statcast for the visible page only, in one batched request.
  const advKey = showAdvanced
    ? paginatedPlayers.map((p) => `${p.name}|${isPitcher(p.position) ? 1 : 0}`).join(",")
    : "";
  useEffect(() => {
    if (!showAdvanced || !advKey) {
      setAdvData(null);
      return;
    }
    let cancelled = false;
    setAdvLoading(true);
    setAdvError("");
    lookupStatcast(
      advKey.split(",").filter(Boolean).map((token) => {
        const idx = token.lastIndexOf("|");
        return { name: token.slice(0, idx), is_pitcher: token.slice(idx + 1) === "1" };
      }),
      typeof advWindow === "number" ? advWindow : 15,
    )
      .then((res) => {
        if (!cancelled) setAdvData(res);
      })
      .catch((e) => {
        if (!cancelled) setAdvError(e instanceof Error ? e.message : "進階數據載入失敗");
      })
      .finally(() => {
        if (!cancelled) setAdvLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showAdvanced, advKey, advWindow]);

  // Which aggregate the advanced cells read from
  const advProfileOf = useCallback(
    (name: string) => {
      const entry = advData?.results[name];
      if (!entry) return null;
      return advWindow === "season" ? entry.season : entry.recent;
    },
    [advData, advWindow],
  );

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
      className={`sticky top-0 z-20 cursor-pointer select-none whitespace-nowrap bg-gray-50 px-2 py-2 text-left text-xs font-medium uppercase text-gray-500 hover:text-gray-700 ${className}`}
      onClick={() => handleSort(col)}
    >
      {label}
      <SortArrow col={col} />
    </th>
  );


  // ============================================================
  // Prospects tab state
  // ============================================================
  const {
    data: prospectsData,
    error: prospectsErr,
    isLoading: prospectsLoading,
    mutate: mutateProspects,
  } = useSWR(
    activeTab === "prospects" && effectiveYear ? `prospects-${effectiveYear}` : null,
    () => getProspects(effectiveYear),
  );

  const [prospectSearch, setProspectSearch] = useState("");
  const [prospectPosFilter, setProspectPosFilter] = useState("ALL");
  const [prospectOwnerFilter, setProspectOwnerFilter] = useState<"all" | "owned" | "fa">("all");

  // Commissioner: prospects reload
  const [prospectsReloading, setProspectsReloading] = useState(false);
  const [prospectsReloadMsg, setProspectsReloadMsg] = useState("");

  const handleReloadProspects = useCallback(async () => {
    setProspectsReloading(true);
    setProspectsReloadMsg("");
    try {
      const result = await reloadProspects();
      setProspectsReloadMsg(result.message);
      mutateProspects();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Reload failed";
      setProspectsReloadMsg(`Error: ${msg}`);
    } finally {
      setProspectsReloading(false);
    }
  }, [mutateProspects]);

  // Client-side filtering for prospects (only ~100 rows, no need for server-side)
  const filteredProspects = useMemo(() => {
    if (!prospectsData?.prospects) return [];
    let list = prospectsData.prospects;

    // Search filter (instant, no Enter needed)
    if (prospectSearch.trim()) {
      const q = prospectSearch.trim().toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.mlb_team.toLowerCase().includes(q) ||
          p.owner_manager.toLowerCase().includes(q),
      );
    }

    // Position filter
    // MLB Pipeline uses LHP/RHP; map SP->also match LHP/RHP, RP->also match LHP/RHP
    if (prospectPosFilter !== "ALL") {
      if (prospectPosFilter === "BATTER") {
        list = list.filter((p) => !isPitcher(p.position));
      } else if (prospectPosFilter === "PITCHER") {
        list = list.filter((p) => isPitcher(p.position));
      } else {
        // Build expanded set: SP also matches LHP/RHP (most prospects are starters)
        const expandedFilter: string[] = [prospectPosFilter];
        if (prospectPosFilter === "SP") {
          expandedFilter.push("LHP", "RHP");
        } else if (prospectPosFilter === "RP") {
          expandedFilter.push("LHP", "RHP");
        } else if (prospectPosFilter === "P") {
          expandedFilter.push("LHP", "RHP", "SP", "RP");
        }
        list = list.filter((p) => {
          const positions = p.position.split(/[,/]/).map((s) => s.trim().toUpperCase());
          return positions.some((pos) => expandedFilter.includes(pos));
        });
      }
    }

    // Ownership filter
    if (prospectOwnerFilter === "owned") {
      list = list.filter((p) => p.owner_manager && p.owner_manager !== "FA");
    } else if (prospectOwnerFilter === "fa") {
      list = list.filter((p) => !p.owner_manager || p.owner_manager === "FA");
    }

    return list;
  }, [prospectsData, prospectSearch, prospectPosFilter, prospectOwnerFilter]);

  // ============================================================
  // Render
  // ============================================================
  return (
    <div className="mx-auto max-w-[100rem] px-4 py-6">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
          {activeTab === "database"
            ? "球員資料庫 Player Database"
            : "百大新秀 Top 100 Prospects"}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {activeTab === "database"
            ? `${data?.total_count ?? 0} 位球員${data?.has_rankings ? " (含 Yahoo 排名)" : ""}`
            : prospectsData
              ? `${prospectsData.source} | 更新: ${prospectsData.updated_at} | ${prospectsData.total_count} 名新秀`
              : "載入中..."}
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="mb-5 flex gap-1 border-b border-gray-200">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 bg-indigo-600" />
            )}
          </button>
        ))}
      </div>

      {/* ========== Database Tab ========== */}
      {activeTab === "database" && (
        <>
          {loading ? (
            <div className="flex min-h-[50vh] items-center justify-center">
              <LoadingSpinner />
            </div>
          ) : error ? (
            <div className="rounded-lg bg-red-50 p-4 text-red-800">{error}</div>
          ) : (
            <>
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

                      {/* Column Guide (auth-only columns hidden for public) */}
                      <div>
                        <h3 className="mb-2 font-semibold text-blue-800">
                          欄位說明 Column Guide
                        </h3>
                        <ul className="space-y-1 text-xs">
                          {isAuth ? (
                            <>
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
                            </>
                          ) : (
                            <li className="text-gray-500">
                              登入後可查看合約、薪資、歸屬等欄位
                            </li>
                          )}
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

              {/* Login hint banner (unauthenticated) */}
              {!isAuth && (
                <div className="mb-4 flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
                  <svg className="h-5 w-5 flex-shrink-0 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                  </svg>
                  <span className="text-sm text-indigo-700">
                    登入後可查看球員持有狀態與合約資訊
                  </span>
                  <a
                    href={`${process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002"}/api/auth/yahoo/login`}
                    className="ml-auto whitespace-nowrap rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500"
                  >
                    Login with Yahoo
                  </a>
                </div>
              )}

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

                  {/* Owner dropdown (auth only) */}
                  {isAuth && (
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
                  )}

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
                    placeholder={isAuth ? "搜尋球員或經理 (Enter)" : "搜尋球員 (Enter)"}
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
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500">
                <span>
                  篩選結果 {data?.total_count ?? 0} 位球員
                  {totalPages > 1 && (
                    <span className="ml-2">
                      (第 {currentPage}/{totalPages} 頁，顯示 {paginatedPlayers.length} 筆)
                    </span>
                  )}
                </span>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => setShowHitting(v => !v)}
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
                      effectiveShowHitting
                        ? "bg-blue-100 text-blue-700"
                        : "bg-gray-100 text-gray-400"
                    } ${positionFilter === "PITCHER" ? "opacity-40 cursor-not-allowed" : ""}`}
                    disabled={positionFilter === "PITCHER"}
                  >
                    {effectiveShowHitting ? "Hide" : "Show"} 打擊
                  </button>
                  <button
                    onClick={() => setShowPitching(v => !v)}
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
                      effectiveShowPitching
                        ? "bg-cyan-100 text-cyan-700"
                        : "bg-gray-100 text-gray-400"
                    } ${positionFilter === "BATTER" ? "opacity-40 cursor-not-allowed" : ""}`}
                    disabled={positionFilter === "BATTER"}
                  >
                    {effectiveShowPitching ? "Hide" : "Show"} 投球
                  </button>
                  <button
                    onClick={() => setShowAdvanced((v) => !v)}
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
                      showAdvanced
                        ? "bg-violet-100 text-violet-700"
                        : "bg-gray-100 text-gray-400"
                    }`}
                    title="顯示 Baseball Savant 進階數據：擊球品質與制球宰制力"
                  >
                    {showAdvanced ? "Hide" : "Show"} 進階數據
                  </button>
                  {showAdvanced && (
                    <select
                      value={String(advWindow)}
                      onChange={(e) =>
                        setAdvWindow(
                          e.target.value === "season" ? "season" : Number(e.target.value),
                        )
                      }
                      className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium text-violet-700"
                    >
                      <option value="7">近 7 天</option>
                      <option value="15">近 15 天</option>
                      <option value="30">近 30 天</option>
                      <option value="season">本季</option>
                    </select>
                  )}
                </div>
              </div>

              {/* Advanced stats legend + status */}
              {showAdvanced && (
                <div className="mb-2 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium">進階數據 Statcast</span>
                    {advLoading && <span className="text-violet-600">載入中...</span>}
                    {advError && <span className="text-rose-600">{advError}</span>}
                    {advData && !advLoading && advWindow !== "season" && (
                      <span className="text-violet-700">
                        區間 {advData.window.start} ~ {advData.window.end}
                        （近 {advData.window.days} 天）· 本頁 {advData.matched}/{advData.requested} 位有資料
                      </span>
                    )}
                    {advData && !advLoading && advWindow === "season" && (
                      <span className="text-violet-700">
                        本季 {advData.season_window?.coverage_start ?? advData.season_window?.start} ~{" "}
                        {advData.season_window?.end} · 本頁 {advData.matched}/{advData.requested} 位有資料
                        {advData.season_window?.coverage_start &&
                          advData.season_window.coverage_start > advData.season_window.start && (
                            <span className="ml-1 text-amber-600">
                              ⚠ 資料僅回補到 {advData.season_window.coverage_start}，尚非完整球季，
                              可請 Commissioner 觸發整季回補
                            </span>
                          )}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 space-y-0.5 text-[11px] text-violet-800">
                    <div>
                      <span className="text-emerald-600">★</span> = 實際 wOBA 落後預期 xwOBA 達{" "}
                      {BUY_SIGNAL_STRONG.toFixed(2).replace(/^0/, "")} 以上：擊球品質好但成績還沒反映，
                      <span className="font-medium">買點訊號強</span>。
                      <span className="ml-1 text-emerald-500">·</span> = 落後{" "}
                      {BUY_SIGNAL_MILD.toFixed(2).replace(/^0/, "")} 以上，訊號較弱。
                    </div>
                    <div className="text-violet-600">
                      欄位名稱可 hover 看說明。此區數據依上方選單為滾動區間或本季，與左側 Yahoo 成績的區間不同；
                      進階欄位不支援排序（排序由後端處理），需要排名請用「雷達 Radar」頁。
                    </div>
                  </div>
                </div>
              )}

              {/* Data freshness — quiet when current, loud when stale so a
                  silent pipeline outage is visible on day one, not day 22 */}
              {data?.last_fetched_at && (() => {
                const ageHours =
                  (Date.now() - new Date(data.last_fetched_at).getTime()) / 3_600_000;
                if (isNaN(ageHours)) return null;
                if (ageHours >= 48) {
                  return (
                    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
                      <span className="font-semibold">
                        數據更新於 {new Date(data.last_fetched_at).toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}
                        （{Math.round(ageHours / 24)} 天前）
                      </span>
                      <span>資料可能過期。</span>
                    </div>
                  );
                }
                return (
                  <p className="mb-2 flex items-center gap-1.5 text-xs text-green-700">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-500" />
                    數據更新於 {new Date(data.last_fetched_at).toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}（每日 18:00 自動更新）
                  </p>
                );
              })()}

              {/* Mobile-only reminder that the table scrolls sideways */}
              <p className="mb-1 text-center text-[11px] text-gray-400 sm:hidden">
                ← 表格可左右滑動查看更多欄位 →
              </p>

              {/* Stats mismatch hint */}
              {data?.stats_sort_type && sortType !== data.stats_sort_type && (
                <div className="mb-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
                  目前無「{SORT_TYPE_OPTIONS.find((o) => o.value === sortType)?.label}」的成績數據。
                  需由 Commissioner 以此選項重新擷取 Yahoo 排名。
                  已有數據：{SORT_TYPE_OPTIONS.find((o) => o.value === data.stats_sort_type)?.label ?? data.stats_sort_type}
                </div>
              )}

              {/* Table — header sticks to the top, rank/player/pos columns stick
                  to the left so stats stay comparable while scrolling */}
              <div className="max-h-[70vh] overflow-auto rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <SortTh col="o_rank" label="OR" className="w-12 left-0 z-30" />
                      <SortTh col="ar_rank" label="AR" className="hidden sm:table-cell w-12 sm:left-12 sm:z-30" />
                      <SortTh col="name" label="球員" className="left-12 sm:left-24 z-30 w-40" />
                      <th className="sticky top-0 left-[13rem] sm:left-[16rem] z-30 whitespace-nowrap border-r border-gray-200 bg-gray-50 px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        Pos
                      </th>
                      <th className="sticky top-0 z-20 hidden md:table-cell whitespace-nowrap bg-gray-50 px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        MLB
                      </th>
                      {isAuth && (
                        <th className="sticky top-0 z-20 bg-gray-50 px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                          {effectiveYear}
                        </th>
                      )}
                      {isAuth && (
                        <th className="sticky top-0 z-20 bg-gray-50 px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                          {effectiveYear + 1}
                        </th>
                      )}
                      {isAuth && <SortTh col="salary" label="$" />}
                      {isAuth && (
                        <th className="sticky top-0 z-20 whitespace-nowrap bg-gray-50 px-2 py-2 text-left text-xs font-medium uppercase text-gray-500">
                          歸屬
                        </th>
                      )}

                      {/* Hitting stats columns */}
                      {effectiveShowHitting && HITTING_COLS.map((c) => (
                        <SortTh
                          key={c.key}
                          col={c.key as SortKey}
                          label={c.label}
                          className=""
                        />
                      ))}
                      {/* Pitching stats columns */}
                      {effectiveShowPitching && PITCHING_COLS.map((c) => (
                        <SortTh
                          key={c.key}
                          col={c.key as SortKey}
                          label={c.label}
                          className=""
                        />
                      ))}

                      {/* Advanced (Statcast) columns — not sortable: these are
                          joined client-side, while sorting happens server-side. */}
                      {showAdvanced && effectiveShowHitting && ADV_BATTING_COLS.map((c) => (
                        <th
                          key={`adv-b-${c.key}`}
                          title={metricTooltip(c.glossary as MetricKey)}
                          className="sticky top-0 z-20 cursor-help whitespace-nowrap bg-violet-50 px-2 py-2 text-right text-xs font-medium uppercase text-violet-700"
                        >
                          {c.label}
                        </th>
                      ))}
                      {showAdvanced && effectiveShowPitching && ADV_PITCHING_COLS.map((c) => (
                        <th
                          key={`adv-p-${c.key}`}
                          title={metricTooltip(c.glossary as MetricKey)}
                          className="sticky top-0 z-20 cursor-help whitespace-nowrap bg-violet-50 px-2 py-2 text-right text-xs font-medium uppercase text-violet-700"
                        >
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {paginatedPlayers.map((p, idx) => {
                      const pitcher = isPitcher(p.position);
                      // Only show stats when the selected sortType matches what was fetched
                      const storedSortType = data?.stats_sort_type ?? "prev_season";
                      const statsMatch = sortType === storedSortType;
                      const statSource = statsMatch ? p.stats : {};

                      return (
                        <tr
                          key={`${p.yahoo_player_id || p.name}-${idx}`}
                          className="group hover:bg-gray-50"
                        >
                          {/* OR (Overall Rank) — frozen */}
                          <td className="sticky left-0 z-10 whitespace-nowrap bg-white px-2 py-1.5 text-gray-400 group-hover:bg-gray-50">
                            {p.o_rank ?? "-"}
                          </td>

                          {/* AR (Actual Rank) — frozen */}
                          <td className="hidden sm:table-cell sm:sticky sm:left-12 sm:z-10 whitespace-nowrap bg-white px-2 py-1.5 text-xs text-gray-500 group-hover:bg-gray-50">
                            {p.ar_rank ?? "-"}
                          </td>

                          {/* Player name — frozen, fixed width so Pos offset stays aligned */}
                          <td className="sticky left-12 sm:left-24 z-10 w-40 max-w-40 bg-white px-2 py-1.5 font-medium group-hover:bg-gray-50">
                            <span className="flex items-center gap-1">
                              <button
                                onClick={() =>
                                  setModalPlayer({ name: p.name, position: p.position })
                                }
                                className="truncate py-2 -my-2 text-left text-indigo-600 hover:text-indigo-800 hover:underline"
                                title={p.name}
                              >
                                {p.name}
                              </button>
                              <StatusBadge status={p.status} />
                            </span>
                          </td>

                          {/* Position — frozen, right edge of the frozen block */}
                          <td className="sticky left-[13rem] sm:left-[16rem] z-10 whitespace-nowrap border-r border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 group-hover:bg-gray-50">
                            {p.position}
                          </td>

                          {/* MLB Team */}
                          <td className="hidden md:table-cell whitespace-nowrap px-2 py-1.5 text-xs text-gray-500">
                            {p.mlb_team || "-"}
                          </td>

                          {/* Current-year contract (auth only) */}
                          {isAuth && (
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
                          )}

                          {/* Next-year projection (auth only) */}
                          {isAuth && (
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
                          )}

                          {/* Salary (auth only) */}
                          {isAuth && (
                            <td className="whitespace-nowrap px-2 py-1.5 text-right text-xs">
                              {p.salary > 0 ? `$${p.salary}` : "-"}
                            </td>
                          )}

                          {/* Owner (auth only) */}
                          {isAuth && (
                            <td className="whitespace-nowrap px-2 py-1.5 text-xs text-gray-600">
                              {p.owner_manager || (
                                <span className="text-gray-300">FA</span>
                              )}
                            </td>
                          )}

                          {/* Hitting stats */}
                          {effectiveShowHitting && HITTING_COLS.map((c) => (
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
                          {effectiveShowPitching && PITCHING_COLS.map((c) => (
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

                          {/* Advanced (Statcast) cells */}
                          {showAdvanced && effectiveShowHitting && ADV_BATTING_COLS.map((c) => {
                            const prof = advProfileOf(p.name);
                            const value = pitcher || !prof
                              ? null
                              : (prof[c.key as keyof typeof prof] as number | null);
                            const gap = c.key === "xwoba" && !pitcher
                              ? buySignalGap(prof?.xwoba, prof?.woba)
                              : null;
                            const level = buySignalLevel(gap);
                            return (
                              <td
                                key={`adv-b-${c.key}`}
                                className={`whitespace-nowrap bg-violet-50/40 px-2 py-1.5 text-right text-xs ${
                                  pitcher ? "text-gray-300" : "text-gray-700"
                                }`}
                                title={
                                  level !== "none" && gap !== null
                                    ? `買點：實際 wOBA 落後預期 ${gap.toFixed(3)}，代表擊球品質還沒反映在成績上`
                                    : undefined
                                }
                              >
                                {formatAdvStat(c.key, value)}
                                {level === "strong" && (
                                  <span className="ml-0.5 text-emerald-600">★</span>
                                )}
                                {level === "mild" && (
                                  <span className="ml-0.5 text-emerald-500">·</span>
                                )}
                              </td>
                            );
                          })}
                          {showAdvanced && effectiveShowPitching && ADV_PITCHING_COLS.map((c) => {
                            const prof = advProfileOf(p.name);
                            const value = !pitcher || !prof
                              ? null
                              : (prof[c.key as keyof typeof prof] as number | null);
                            return (
                              <td
                                key={`adv-p-${c.key}`}
                                className={`whitespace-nowrap bg-violet-50/40 px-2 py-1.5 text-right text-xs ${
                                  !pitcher ? "text-gray-300" : "text-gray-700"
                                }`}
                              >
                                {formatAdvStat(c.key, value)}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}

                    {paginatedPlayers.length === 0 && (
                      <tr>
                        <td
                          colSpan={
                            (isAuth ? 9 : 5) +
                            (effectiveShowHitting ? HITTING_COLS.length : 0) +
                            (effectiveShowPitching ? PITCHING_COLS.length : 0) +
                            (showAdvanced && effectiveShowHitting ? ADV_BATTING_COLS.length : 0) +
                            (showAdvanced && effectiveShowPitching ? ADV_PITCHING_COLS.length : 0)
                          }
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
            </>
          )}
        </>
      )}

      {/* ========== Prospects Tab ========== */}
      {activeTab === "prospects" && (
        <>
          {prospectsLoading ? (
            <div className="flex min-h-[50vh] items-center justify-center">
              <LoadingSpinner />
            </div>
          ) : prospectsErr ? (
            <div className="rounded-lg bg-red-50 p-4 text-red-800">
              {prospectsErr?.message || "Failed to load prospects data"}
            </div>
          ) : (
            <>
              {/* Controls Row */}
              <div className="mb-4 flex flex-wrap items-center gap-2">
                {/* Search (instant, no Enter needed) */}
                <input
                  type="text"
                  placeholder={isAuth ? "搜尋新秀名稱 / 球隊 / 經理" : "搜尋新秀名稱 / 球隊"}
                  value={prospectSearch}
                  onChange={(e) => setProspectSearch(e.target.value)}
                  className="w-56 rounded-md border border-gray-300 px-3 py-1.5 text-sm placeholder-gray-400 focus:border-indigo-500 focus:ring-indigo-500"
                />

                {/* Position dropdown */}
                <select
                  value={prospectPosFilter}
                  onChange={(e) => setProspectPosFilter(e.target.value)}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                >
                  {POSITION_GROUPS.map((pg) => (
                    <option key={pg.value} value={pg.value}>
                      {pg.value === "ALL" ? "All Positions" : pg.label}
                    </option>
                  ))}
                </select>

                {/* Ownership filter (auth only) */}
                {isAuth && (
                  <select
                    value={prospectOwnerFilter}
                    onChange={(e) =>
                      setProspectOwnerFilter(
                        e.target.value as "all" | "owned" | "fa",
                      )
                    }
                    className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  >
                    {PROSPECT_OWNER_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                )}

                <span className="ml-auto text-sm text-gray-500">
                  {filteredProspects.length} / {prospectsData?.total_count ?? 0}{" "}
                  名新秀
                </span>
              </div>

              {/* Login hint banner for prospects (unauthenticated) */}
              {!isAuth && (
                <div className="mb-4 flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
                  <svg className="h-5 w-5 flex-shrink-0 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
                  </svg>
                  <span className="text-sm text-indigo-700">
                    登入後可查看新秀持有狀態與合約資訊
                  </span>
                  <a
                    href={`${process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002"}/api/auth/yahoo/login`}
                    className="ml-auto whitespace-nowrap rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500"
                  >
                    Login with Yahoo
                  </a>
                </div>
              )}

              {/* Commissioner: Reload Prospects */}
              {isCommissioner && (
                <div className="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 p-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="rounded bg-yellow-600 px-2 py-0.5 text-xs font-semibold text-white">
                      CM
                    </span>
                    <button
                      onClick={handleReloadProspects}
                      disabled={prospectsReloading}
                      className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                    >
                      {prospectsReloading ? "重新載入中..." : "重新載入 JSON"}
                    </button>
                    <span className="text-xs text-gray-600">
                      資料來源: {prospectsData?.source ?? "-"} | 更新日期:{" "}
                      {prospectsData?.updated_at ?? "-"}
                    </span>
                    {prospectsReloadMsg && (
                      <span
                        className={`text-xs ${
                          prospectsReloadMsg.startsWith("Error")
                            ? "text-red-600"
                            : "text-green-600"
                        }`}
                      >
                        {prospectsReloadMsg}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Prospects Table */}
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="w-12 whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        #
                      </th>
                      <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        球員
                      </th>
                      <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        Pos
                      </th>
                      <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        MLB
                      </th>
                      <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        Age
                      </th>
                      <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        ETA
                      </th>
                      {isAuth && (
                        <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                          歸屬
                        </th>
                      )}
                      {isAuth && (
                        <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                          合約
                        </th>
                      )}
                      <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        備註
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {filteredProspects.map((p) => (
                      <tr key={p.rank} className="hover:bg-gray-50">
                        {/* Rank */}
                        <td className="whitespace-nowrap px-3 py-2 text-sm font-semibold text-gray-700">
                          {p.rank}
                        </td>

                        {/* Player name */}
                        <td className="whitespace-nowrap px-3 py-2 font-medium">
                          <button
                            onClick={() =>
                              setModalPlayer({
                                name: p.name,
                                position: p.position,
                              })
                            }
                            className="py-2 -my-2 text-left text-indigo-600 hover:text-indigo-800 hover:underline"
                          >
                            {p.name}
                          </button>
                        </td>

                        {/* Position */}
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-gray-600">
                          {p.position}
                        </td>

                        {/* MLB Team */}
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-gray-500">
                          {p.mlb_team}
                        </td>

                        {/* Age */}
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-gray-500">
                          {p.age ?? "-"}
                        </td>

                        {/* ETA */}
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-gray-500">
                          {p.eta ?? "-"}
                        </td>

                        {/* Owner (auth only) */}
                        {isAuth && (
                          <td className="whitespace-nowrap px-3 py-2 text-xs">
                            {p.owner_manager &&
                            p.owner_manager !== "FA" ? (
                              <span className="font-medium text-gray-700">
                                {p.owner_manager}
                              </span>
                            ) : (
                              <span className="text-gray-300">FA</span>
                            )}
                          </td>
                        )}

                        {/* Contract (auth only) */}
                        {isAuth && (
                          <td className="whitespace-nowrap px-3 py-2">
                            {p.contract_display &&
                            p.contract_type !== "FA" ? (
                              <ContractBadge
                                type={p.contract_type as ContractType}
                                display={p.contract_display}
                              />
                            ) : (
                              <span className="text-xs text-gray-300">
                                -
                              </span>
                            )}
                          </td>
                        )}

                        {/* Note */}
                        <td className="max-w-[200px] truncate px-3 py-2 text-xs text-gray-500">
                          {p.note ?? ""}
                        </td>
                      </tr>
                    ))}

                    {filteredProspects.length === 0 && (
                      <tr>
                        <td
                          colSpan={isAuth ? 9 : 7}
                          className="py-8 text-center text-gray-400"
                        >
                          沒有符合條件的新秀
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {/* Player Stats Modal (shared between tabs) */}
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
