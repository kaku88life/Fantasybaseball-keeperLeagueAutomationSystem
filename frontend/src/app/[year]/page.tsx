"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import {
  getKeeperResults,
  getLeagueSummary,
  getTeams,
  getYears,
} from "@/lib/api";
import type { KeeperResultTeam } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import LoadingSpinner from "@/components/LoadingSpinner";
import AuthGate from "@/components/AuthGate";
import type { DBTeam } from "@/types";

interface TeamSummary {
  manager_name: string;
  team_name: string;
  active_keepers: number;
  farm_rookies: number;
  total_keeper_cost: number;
  available_salary: number;
  available_faab: number;
  salary_cap: number;
  ranking_bonus: number;
  line_name?: string;
  mlb_team_counts?: [string, number][];
}

// Total roster slots (active + pitchers + bench), excluding NA and DL
const TOTAL_ROSTER_SLOTS = 27;

// Derive previous-year ranking from ranking_bonus
function getRanking(bonus: number): number | null {
  const map: Record<number, number> = { 10: 1, 7: 2, 5: 3, 3: 4, 2: 5, 1: 6 };
  return map[bonus] ?? null;
}

type TabKey = "season-end" | "keepers" | "in-season";

export default function YearOverviewPage() {
  return (
    <AuthGate>
      <YearOverviewContent />
    </AuthGate>
  );
}

function YearOverviewContent() {
  const params = useParams();
  const year = Number(params.year);
  const { user } = useAuth();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<TabKey>("season-end");

  // SWR cached data fetches
  const { data: years = [] } = useSWR("years", getYears);
  const { data: dbTeams = [] } = useSWR("teams", getTeams);
  const { data: summary, error: summaryErr } = useSWR(
    year ? `summary-${year}` : null,
    () => getLeagueSummary(year),
  );
  const { data: keeperResults, isLoading: keeperLoading } = useSWR(
    activeTab === "keepers" && year ? `keeper-results-${year}` : null,
    () => getKeeperResults(year),
  );

  // In-season tab: fetch next year's snapshot (which contains current season Yahoo roster)
  const { data: inSeasonSummary, isLoading: inSeasonLoading } = useSWR(
    activeTab === "in-season" && year ? `summary-${year + 1}` : null,
    () => getLeagueSummary(year + 1),
  );

  // Hide "next year" from dropdown until keeper selections start for that year
  const currentSeasonYear = new Date().getFullYear();
  const visibleYears = years.filter((y) => y <= currentSeasonYear);

  const error = summaryErr?.message || "";

  // Find DB team id by manager name
  const findTeamId = (managerName: string): number | null => {
    const t = dbTeams.find((t) => t.manager_name === managerName);
    return t ? t.id : null;
  };

  if (error) {
    return (
      <div className="py-10 text-center">
        <p className="text-red-600">{error}</p>
        {years.length > 0 && (
          <div className="mt-4">
            <p className="text-sm text-gray-500">切換賽季：</p>
            <div className="mt-2 flex justify-center gap-2">
              {[...visibleYears].reverse().map((y) => (
                <Link
                  key={y}
                  href={`/${y}`}
                  className="rounded bg-gray-200 px-3 py-1 text-sm hover:bg-gray-300"
                >
                  {y} 賽季
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (!summary) {
    return <LoadingSpinner />;
  }

  const tabs: { key: TabKey; label: string; sublabel: string }[] = [
    {
      key: "season-end",
      label: `${year - 1} 賽季名單`,
      sublabel: "Season-End Roster",
    },
    {
      key: "keepers",
      label: `${year} 賽季前 Keepers`,
      sublabel: "Pre-Season Keepers",
    },
    {
      key: "in-season",
      label: `${year} 賽季中名單`,
      sublabel: "In-Season Roster",
    },
  ];

  return (
    <div>
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold sm:text-2xl">{year} 賽季</h1>
          <div className="flex items-center gap-1.5 sm:gap-2">
            {user && (
              <Link
                href="/commissioner"
                className={`rounded px-2.5 py-1 text-xs font-medium sm:px-3 sm:text-sm ${
                  user.is_commissioner
                    ? "bg-yellow-500 text-white hover:bg-yellow-400"
                    : "bg-gray-500 text-white hover:bg-gray-400"
                }`}
              >
                Commissioner
              </Link>
            )}
            {visibleYears.length > 0 && (
              <select
                value={year}
                onChange={(e) => router.push(`/${e.target.value}`)}
                className="rounded border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:px-3 sm:text-sm"
              >
                {[...visibleYears].reverse().map((y) => (
                  <option key={y} value={y}>{y} 賽季</option>
                ))}
              </select>
            )}
          </div>
        </div>
        <p className="mt-1 text-sm text-gray-500">
          薪資上限: ${summary.salary_cap} | {summary.teams.length} 隊
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex border-b overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`min-h-[44px] whitespace-nowrap px-3 py-2 text-xs font-medium transition sm:min-h-0 sm:px-4 sm:text-sm ${
              activeTab === tab.key
                ? "border-b-2 border-indigo-600 text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            <span className="ml-1 hidden text-xs text-gray-400 sm:inline">{tab.sublabel}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "season-end" && (
        <SeasonEndTab
          summary={summary}
          user={user}
          year={year}
          findTeamId={findTeamId}
        />
      )}
      {activeTab === "keepers" && (
        <KeepersTab
          keeperResults={keeperResults ?? null}
          loading={keeperLoading}
          user={user}
          year={year}
        />
      )}
      {activeTab === "in-season" && (
        inSeasonLoading ? <LoadingSpinner /> :
        inSeasonSummary ? (
          <SeasonEndTab
            summary={inSeasonSummary}
            user={user}
            year={year}
            findTeamId={findTeamId}
            showMlbTeams
          />
        ) : (
          <div className="py-10 text-center text-gray-400 text-sm">
            {year} 賽季中名單尚未建立
            <br />
            <span className="text-xs">Commissioner 可透過「同步名冊」功能匯入最新 Yahoo 名冊</span>
          </div>
        )
      )}
    </div>
  );
}

/* ========== Season-End Tab (existing content) ========== */

function SeasonEndTab({
  summary,
  user,
  year,
  findTeamId,
  showMlbTeams = false,
}: {
  summary: { teams: TeamSummary[] };
  user: { manager_name?: string | null } | null;
  year: number;
  findTeamId: (name: string) => number | null;
  showMlbTeams?: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 sm:gap-4">
      {summary.teams.map((t) => {
        const teamId = findTeamId(t.manager_name);
        const isMyTeam = user?.manager_name === t.manager_name;
        const ranking = getRanking(t.ranking_bonus);

        return (
          <Link
            key={t.manager_name}
            href={teamId ? `/${year}/${teamId}` : "#"}
            className={`block rounded-lg border p-3 transition hover:shadow-md sm:p-4 ${
              isMyTeam
                ? "border-indigo-300 bg-indigo-50"
                : ranking === 1
                  ? "border-yellow-300 bg-yellow-50"
                  : "border-gray-200 bg-white"
            }`}
          >
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                {ranking === 1 && <span className="text-base">&#x1F451;</span>}
                {ranking && ranking > 1 && (
                  <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs font-bold text-gray-600">
                    #{ranking}
                  </span>
                )}
                <h3 className="truncate text-sm font-semibold sm:text-base">{t.manager_name}</h3>
                {t.line_name && (
                  <span className="truncate text-xs text-gray-400">
                    ({t.line_name})
                  </span>
                )}
              </div>
              {isMyTeam && (
                <span className="shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">
                  我的隊伍
                </span>
              )}
            </div>
            {t.team_name && (
              <p className="mb-2 text-xs text-gray-500">{t.team_name}</p>
            )}
            <div className="space-y-1 text-xs sm:text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">球員:</span>
                <span>
                  {t.active_keepers}
                  {t.farm_rookies > 0 && (
                    <span className="text-gray-400"> +{t.farm_rookies}R</span>
                  )}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">團隊薪資:</span>
                <span className="font-medium">${t.total_keeper_cost}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">可用薪資:</span>
                <span
                  className={
                    t.available_salary < 20
                      ? "font-medium text-red-600"
                      : "text-green-700"
                  }
                >
                  ${t.available_salary}
                </span>
              </div>
              {t.ranking_bonus > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-500">排名獎勵:</span>
                  <span className="text-yellow-600">+${t.ranking_bonus}</span>
                </div>
              )}
            </div>
            {/* MLB team distribution (top teams with 2+ players) */}
            {t.mlb_team_counts && t.mlb_team_counts.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1 border-t pt-2">
                {t.mlb_team_counts.map(([team, count]) => (
                  <span
                    key={team}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                      count >= 5
                        ? "bg-green-200 text-green-800"
                        : count >= 3
                          ? "bg-amber-200 text-amber-800"
                          : "bg-gray-200 text-gray-600"
                    }`}
                  >
                    {team} {count}
                  </span>
                ))}
              </div>
            )}
          </Link>
        );
      })}
    </div>
  );
}

/* ========== Keepers Tab (new) ========== */

function KeepersTab({
  keeperResults,
  loading,
  user,
  year,
}: {
  keeperResults: { teams: KeeperResultTeam[] } | null;
  loading: boolean;
  user: { manager_name?: string | null } | null;
  year: number;
}) {
  // Track which teams are expanded (default: all collapsed)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleExpand = (teamId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(teamId)) {
        next.delete(teamId);
      } else {
        next.add(teamId);
      }
      return next;
    });
  };

  const expandAll = () => {
    if (!keeperResults) return;
    setExpandedIds(new Set(keeperResults.teams.map((t) => t.team_id)));
  };

  const collapseAll = () => {
    setExpandedIds(new Set());
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  if (!keeperResults) {
    return (
      <div className="py-10 text-center text-gray-500">
        無法載入 Keepers 名單
      </div>
    );
  }

  const submittedTeams = keeperResults.teams.filter((t) => t.is_submitted);
  const pendingTeams = keeperResults.teams.filter((t) => !t.is_submitted);

  return (
    <div className="space-y-6">
      {/* Summary bar */}
      <div className="flex flex-col gap-2 rounded-lg border bg-gray-50 px-3 py-3 text-sm text-gray-600 sm:flex-row sm:items-center sm:justify-between sm:px-4">
        <div>
          已繳交{" "}
          <span className="font-bold text-indigo-600">
            {submittedTeams.length}
          </span>{" "}
          / {keeperResults.teams.length} 隊
          {pendingTeams.length > 0 && (
            <span className="ml-2 hidden text-gray-400 sm:inline">
              (尚未繳交: {pendingTeams.map((t) => t.manager_name).join(", ")})
            </span>
          )}
        </div>
        {submittedTeams.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={expandAll}
              className="min-h-[44px] rounded px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-50 sm:min-h-0"
            >
              全部展開
            </button>
            <button
              onClick={collapseAll}
              className="min-h-[44px] rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100 sm:min-h-0"
            >
              全部收合
            </button>
          </div>
        )}
      </div>

      {/* Submitted teams */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {submittedTeams.map((team) => {
          const isMyTeam = user?.manager_name === team.manager_name;
          const isExpanded = expandedIds.has(team.team_id);
          // Count active keepers (non-R kept players) and farm rookies
          const activeCount = team.kept_players.filter(
            (p) => p.next_contract && !p.next_contract.includes("/R")
          ).length;
          const farmCount = team.kept_players.filter(
            (p) => p.next_contract && p.next_contract.includes("/R")
          ).length;

          // Team concentration (2+ players from same MLB team)
          const teamCounts: Record<string, number> = {};
          for (const p of team.kept_players) {
            if (p.mlb_team) {
              teamCounts[p.mlb_team] = (teamCounts[p.mlb_team] || 0) + 1;
            }
          }
          const concentrated = Object.entries(teamCounts)
            .filter(([, c]) => c >= 2)
            .sort((a, b) => b[1] - a[1]);

          return (
            <div
              key={team.team_id}
              className={`rounded-lg border ${
                isMyTeam
                  ? "border-indigo-300 bg-indigo-50"
                  : "border-gray-200 bg-white"
              }`}
            >
              {/* Clickable team header */}
              <button
                onClick={() => toggleExpand(team.team_id)}
                className="flex w-full items-center justify-between px-4 py-3 text-left"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <svg
                    className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${
                      isExpanded ? "rotate-90" : ""
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  <h3 className="truncate font-semibold text-sm sm:text-base">
                    {team.manager_name}
                  </h3>
                  {team.line_name && (
                    <span className="truncate text-xs text-gray-400">
                      ({team.line_name})
                    </span>
                  )}
                  {isMyTeam && (
                    <span className="shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">
                      我的隊伍
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  {concentrated.length > 0 && (
                    <div className="hidden sm:flex gap-0.5">
                      {concentrated.map(([t, c]) => (
                        <span
                          key={t}
                          className={`rounded px-1 py-0.5 text-[10px] font-bold ${
                            c >= 3 ? "bg-amber-200 text-amber-800" : "bg-gray-200 text-gray-600"
                          }`}
                        >
                          {t}:{c}
                        </span>
                      ))}
                    </div>
                  )}
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-mono font-medium text-gray-700">
                    {activeCount}/{TOTAL_ROSTER_SLOTS}
                    {farmCount > 0 && (
                      <span className="text-blue-600"> +{farmCount}R</span>
                    )}
                  </span>
                  <span className="text-xs font-bold">
                    <span
                      className={
                        team.available_salary < 20
                          ? "text-red-600"
                          : "text-green-700"
                      }
                    >
                      ${team.available_salary}
                    </span>
                    {team.buyout_faab_cost > 0 && (
                      <span className="text-gray-400">
                        {" / "}
                        <span
                          className={
                            team.available_faab < 50
                              ? "text-orange-600"
                              : "text-green-700"
                          }
                        >
                          F${team.available_faab}
                        </span>
                      </span>
                    )}
                  </span>
                  <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                    已繳交
                  </span>
                </div>
              </button>

              {/* Expandable content */}
              {isExpanded && (
                <div className="border-t px-4 pb-4 pt-3">
                  {/* Financial summary */}
                  <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    {/* -- Salary Cap section -- */}
                    <div className="flex justify-between">
                      <span className="text-gray-500">留用薪資:</span>
                      <span className="font-medium">${team.keeper_cost}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">薪資上限:</span>
                      <span>${team.salary_cap}</span>
                    </div>
                    {team.buyout_cost > 0 && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">
                          買斷{team.buyout_faab_cost > 0 ? " (薪資帽)" : ""}:
                        </span>
                        <span className="text-red-600">
                          -${team.buyout_cost}
                        </span>
                      </div>
                    )}
                    {team.ranking_bonus > 0 && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">排名獎勵:</span>
                        <span className="text-yellow-600">
                          +${team.ranking_bonus}
                        </span>
                      </div>
                    )}
                    {team.trade_compensation > 0 && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">交易補償:</span>
                        <span className="text-blue-600">
                          +${team.trade_compensation}
                        </span>
                      </div>
                    )}
                    <div className="col-span-2 flex justify-between border-t pt-1">
                      <span className="text-gray-500">可用薪資 Cap Space:</span>
                      <span
                        className={`font-bold ${
                          team.available_salary < 20
                            ? "text-red-600"
                            : "text-green-700"
                        }`}
                      >
                        ${team.available_salary}
                      </span>
                    </div>

                    {/* -- FAAB section (only when buyout has FAAB cost) -- */}
                    {team.buyout_faab_cost > 0 && (
                      <>
                        <div className="col-span-2 mt-1.5 mb-0.5">
                          <span className="font-medium text-gray-600">FAAB</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">FAAB 預算:</span>
                          <span>${team.faab_budget}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">買斷 (FAAB):</span>
                          <span className="text-red-600">
                            -${team.buyout_faab_cost}
                          </span>
                        </div>
                        <div className="col-span-2 flex justify-between border-t pt-1">
                          <span className="text-gray-500">可用 FAAB:</span>
                          <span
                            className={`font-bold ${
                              team.available_faab < 50
                                ? "text-orange-600"
                                : "text-green-700"
                            }`}
                          >
                            ${team.available_faab}
                          </span>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Team concentration (mobile view) */}
                  {concentrated.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1 sm:hidden">
                      {concentrated.map(([t, c]) => (
                        <span
                          key={t}
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            c >= 3 ? "bg-amber-200 text-amber-800" : "bg-gray-200 text-gray-600"
                          }`}
                        >
                          {t}:{c}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Player list */}
                  <div className="space-y-0.5 overflow-x-auto">
                    <div className="flex items-center gap-1 border-b pb-1 text-xs font-medium text-gray-500 sm:gap-2">
                      <span className="min-w-0 flex-1">球員</span>
                      <span className="hidden w-12 shrink-0 text-center sm:block">球隊</span>
                      <span className="hidden w-14 shrink-0 text-center sm:block">位置</span>
                      <span className="w-14 shrink-0 text-center sm:w-16">原合約</span>
                      <span className="w-14 shrink-0 text-center sm:w-16">新合約</span>
                    </div>
                    {team.kept_players.map((p) => (
                      <div
                        key={p.player_name}
                        className="flex items-center gap-1 py-0.5 text-xs sm:gap-2"
                      >
                        <span className="min-w-0 flex-1 truncate font-medium">
                          {p.player_name}
                        </span>
                        <span className="hidden w-12 shrink-0 text-center text-gray-400 sm:block">
                          {p.mlb_team || "-"}
                        </span>
                        <span className="hidden w-14 shrink-0 text-center text-gray-400 sm:block">
                          {p.position || "-"}
                        </span>
                        <span className="w-14 shrink-0 text-center text-gray-500 sm:w-16">
                          {p.current_contract}
                        </span>
                        <span className="w-14 shrink-0 text-center font-medium text-indigo-600 sm:w-16">
                          {p.next_contract}
                        </span>
                      </div>
                    ))}
                    {team.kept_players.length === 0 && (
                      <p className="py-2 text-center text-xs text-gray-400">
                        無留用球員資料
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pending teams */}
      {pendingTeams.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {pendingTeams.map((team) => (
            <div
              key={team.team_id}
              className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-400">
                    {team.manager_name}
                  </h3>
                  {team.line_name && (
                    <span className="text-xs text-gray-300">
                      ({team.line_name})
                    </span>
                  )}
                </div>
                <span className="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-500">
                  尚未繳交
                </span>
              </div>
              <p className="mt-2 text-xs text-gray-400">
                等待 GM 提交 Keepers 名單...
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
