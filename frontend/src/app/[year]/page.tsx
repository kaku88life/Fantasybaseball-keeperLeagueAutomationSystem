"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getKeeperResults,
  getLeagueSummary,
  getTeams,
  getYears,
} from "@/lib/api";
import type { KeeperResultTeam } from "@/lib/api";
import { useAuth } from "@/lib/auth";
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
}

type TabKey = "season-end" | "keepers";

export default function YearOverviewPage() {
  const params = useParams();
  const year = Number(params.year);
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<TabKey>("season-end");
  const [summary, setSummary] = useState<{
    year: number;
    salary_cap: number;
    teams: TeamSummary[];
  } | null>(null);
  const [keeperResults, setKeeperResults] = useState<{
    year: number;
    teams: KeeperResultTeam[];
  } | null>(null);
  const [keeperLoading, setKeeperLoading] = useState(false);
  const [dbTeams, setDbTeams] = useState<DBTeam[]>([]);
  const [years, setYears] = useState<number[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getYears().then(setYears).catch(() => {});
    getTeams().then(setDbTeams).catch(() => {});
  }, []);

  useEffect(() => {
    if (!year) return;
    setError("");
    getLeagueSummary(year)
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, [year]);

  // Load keeper results when tab switches to "keepers"
  useEffect(() => {
    if (activeTab !== "keepers" || !year) return;
    if (keeperResults && keeperResults.year === year) return;
    setKeeperLoading(true);
    getKeeperResults(year)
      .then(setKeeperResults)
      .catch(() => {})
      .finally(() => setKeeperLoading(false));
  }, [activeTab, year, keeperResults]);

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
            <p className="text-sm text-gray-500">Available years:</p>
            <div className="mt-2 flex justify-center gap-2">
              {years.map((y) => (
                <Link
                  key={y}
                  href={`/${y}`}
                  className="rounded bg-gray-200 px-3 py-1 text-sm hover:bg-gray-300"
                >
                  {y}
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (!summary) {
    return <div className="py-10 text-center text-gray-500">Loading...</div>;
  }

  const tabs: { key: TabKey; label: string; sublabel: string }[] = [
    {
      key: "season-end",
      label: `${year - 1} 賽季最終名單`,
      sublabel: "Season-End Roster",
    },
    {
      key: "keepers",
      label: `${year} 賽季前 Keepers`,
      sublabel: "Pre-Season Keepers",
    },
  ];

  return (
    <div>
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold sm:text-2xl">{year} 賽季</h1>
          <div className="flex gap-1.5 sm:gap-2">
            {years.map((y) => (
              <Link
                key={y}
                href={`/${y}`}
                className={`rounded px-2.5 py-1 text-xs sm:px-3 sm:text-sm ${
                  y === year
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-200 hover:bg-gray-300"
                }`}
              >
                {y}
              </Link>
            ))}
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
            className={`whitespace-nowrap px-3 py-2 text-xs font-medium transition sm:px-4 sm:text-sm ${
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
          keeperResults={keeperResults}
          loading={keeperLoading}
          user={user}
          year={year}
        />
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
}: {
  summary: { teams: TeamSummary[] };
  user: { manager_name?: string | null } | null;
  year: number;
  findTeamId: (name: string) => number | null;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 sm:gap-4">
      {summary.teams.map((t) => {
        const teamId = findTeamId(t.manager_name);
        const isMyTeam = user?.manager_name === t.manager_name;

        return (
          <Link
            key={t.manager_name}
            href={teamId ? `/${year}/${teamId}` : "#"}
            className={`block rounded-lg border p-3 transition hover:shadow-md sm:p-4 ${
              isMyTeam
                ? "border-indigo-300 bg-indigo-50"
                : "border-gray-200 bg-white"
            }`}
          >
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold sm:text-base">{t.manager_name}</h3>
              {isMyTeam && (
                <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">
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
  if (loading) {
    return <div className="py-10 text-center text-gray-500">Loading...</div>;
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
      <div className="rounded-lg border bg-gray-50 px-4 py-3 text-sm text-gray-600">
        已繳交{" "}
        <span className="font-bold text-indigo-600">
          {submittedTeams.length}
        </span>{" "}
        / {keeperResults.teams.length} 隊
        {pendingTeams.length > 0 && (
          <span className="ml-2 text-gray-400">
            (尚未繳交: {pendingTeams.map((t) => t.manager_name).join(", ")})
          </span>
        )}
      </div>

      {/* Submitted teams */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {submittedTeams.map((team) => {
          const isMyTeam = user?.manager_name === team.manager_name;

          return (
            <div
              key={team.team_id}
              className={`rounded-lg border p-4 ${
                isMyTeam
                  ? "border-indigo-300 bg-indigo-50"
                  : "border-gray-200 bg-white"
              }`}
            >
              {/* Team header */}
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">{team.manager_name}</h3>
                  {isMyTeam && (
                    <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">
                      我的隊伍
                    </span>
                  )}
                </div>
                <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                  已繳交
                </span>
              </div>

              {/* Financial summary */}
              <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
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
                    <span className="text-gray-500">買斷成本:</span>
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
              </div>

              {/* Player list */}
              <div className="space-y-0.5 overflow-x-auto">
                <div className="flex items-center gap-1 border-b pb-1 text-xs font-medium text-gray-500 sm:gap-2">
                  <span className="min-w-0 flex-1">球員</span>
                  <span className="w-10 shrink-0 text-center sm:w-14">位置</span>
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
                    <span className="w-10 shrink-0 text-center text-gray-400 sm:w-14">
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
                <h3 className="font-semibold text-gray-400">
                  {team.manager_name}
                </h3>
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
