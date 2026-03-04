"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getLeagueSummary, getTeams, getYears } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DBTeam } from "@/types";
import ContractBadge from "@/components/ContractBadge";

interface TeamSummary {
  manager_name: string;
  team_name: string;
  active_keepers: number;
  bench_keepers: number;
  total_keeper_cost: number;
  available_salary: number;
  available_faab: number;
  salary_cap: number;
  ranking_bonus: number;
}

export default function YearOverviewPage() {
  const params = useParams();
  const year = Number(params.year);
  const { user } = useAuth();

  const [summary, setSummary] = useState<{
    year: number;
    salary_cap: number;
    teams: TeamSummary[];
  } | null>(null);
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

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{year} Season</h1>
          <p className="text-sm text-gray-500">
            Salary Cap: ${summary.salary_cap} | {summary.teams.length} Teams
          </p>
        </div>
        <div className="flex gap-2">
          {years.map((y) => (
            <Link
              key={y}
              href={`/${y}`}
              className={`rounded px-3 py-1 text-sm ${
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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {summary.teams.map((t) => {
          const teamId = findTeamId(t.manager_name);
          const isMyTeam = user?.manager_name === t.manager_name;

          return (
            <Link
              key={t.manager_name}
              href={teamId ? `/${year}/${teamId}` : "#"}
              className={`block rounded-lg border p-4 transition hover:shadow-md ${
                isMyTeam
                  ? "border-indigo-300 bg-indigo-50"
                  : "border-gray-200 bg-white"
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <h3 className="font-semibold">{t.manager_name}</h3>
                {isMyTeam && (
                  <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">
                    My Team
                  </span>
                )}
              </div>
              {t.team_name && (
                <p className="mb-2 text-xs text-gray-500">{t.team_name}</p>
              )}
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Keepers:</span>
                  <span>
                    {t.active_keepers} active
                    {t.bench_keepers > 0 && ` + ${t.bench_keepers} bench`}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Keeper Cost:</span>
                  <span className="font-medium">${t.total_keeper_cost}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Available:</span>
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
                    <span className="text-gray-500">Rank Bonus:</span>
                    <span className="text-yellow-600">+${t.ranking_bonus}</span>
                  </div>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
