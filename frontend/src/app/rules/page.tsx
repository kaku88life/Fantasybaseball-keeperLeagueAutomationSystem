"use client";

import { useEffect, useState } from "react";
import { getLeagueSettings } from "@/lib/api";
import type { LeagueSettings } from "@/types";

export default function RulesPage() {
  const [settings, setSettings] = useState<LeagueSettings | null>(null);

  useEffect(() => {
    getLeagueSettings().then(setSettings).catch(() => {});
  }, []);

  if (!settings) {
    return <div className="py-10 text-center text-gray-500">Loading...</div>;
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-6 text-2xl font-bold">League Rules</h1>

      <div className="space-y-6">
        {/* Basic Info */}
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold">Basic Info</h2>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-gray-500">League:</dt>
            <dd>{settings.league_name}</dd>
            <dt className="text-gray-500">Teams:</dt>
            <dd>{settings.total_teams}</dd>
            <dt className="text-gray-500">Format:</dt>
            <dd>{settings.scoring_format}</dd>
            <dt className="text-gray-500">Hitting:</dt>
            <dd>{settings.hitting_cats.join(", ")}</dd>
            <dt className="text-gray-500">Pitching:</dt>
            <dd>{settings.pitching_cats.join(", ")}</dd>
          </dl>
        </section>

        {/* Salary Cap */}
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold">Salary Cap</h2>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-gray-500">Base:</dt>
            <dd>${settings.salary_base}</dd>
            <dt className="text-gray-500">Yearly Increase:</dt>
            <dd>+${settings.salary_increment}/year (starting 2024)</dd>
            <dt className="text-gray-500">FAAB Budget:</dt>
            <dd>${settings.faab_base}</dd>
            <dt className="text-gray-500">Min Bid:</dt>
            <dd>${settings.min_bid}</dd>
          </dl>
        </section>

        {/* Keeper Rules */}
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold">Keeper Rules</h2>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-gray-500">Active Keepers:</dt>
            <dd>
              {settings.keeper_active_min}-{settings.keeper_active_max}
            </dd>
            <dt className="text-gray-500">Bench (R):</dt>
            <dd>Max {settings.keeper_bench_max}</dd>
            <dt className="text-gray-500">Extension Cost:</dt>
            <dd>+${settings.extension_cost_per_year}/year</dd>
          </dl>
        </section>

        {/* Contract Flow */}
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold">Contract Flow</h2>
          <div className="space-y-2 text-sm">
            <p>
              <span className="rounded bg-blue-100 px-1.5 py-0.5 font-medium text-blue-800">
                A
              </span>{" "}
              1st year (draft/FAAB) &rarr;{" "}
              <span className="rounded bg-green-100 px-1.5 py-0.5 font-medium text-green-800">
                B
              </span>{" "}
              2nd year
            </p>
            <p>
              <span className="rounded bg-green-100 px-1.5 py-0.5 font-medium text-green-800">
                B
              </span>{" "}
              &rarr;{" "}
              <span className="rounded bg-red-100 px-1.5 py-0.5 font-medium text-red-800">
                O
              </span>{" "}
              Option year (then FA)
            </p>
            <p>
              <span className="rounded bg-green-100 px-1.5 py-0.5 font-medium text-green-800">
                B
              </span>{" "}
              &rarr;{" "}
              <span className="rounded bg-orange-100 px-1.5 py-0.5 font-medium text-orange-800">
                N(x)+O
              </span>{" "}
              Extension (salary + N*$5)
            </p>
            <p>
              <span className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-800">
                R
              </span>{" "}
              Rookie (bench only) &rarr; Activate as A
            </p>
          </div>
        </section>

        {/* Ranking Bonus */}
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-lg font-semibold">Ranking Bonus</h2>
          <div className="grid grid-cols-3 gap-2 text-sm">
            {Object.entries(settings.ranking_bonus)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([rank, bonus]) => (
                <div key={rank}>
                  <span className="text-gray-500">#{rank}:</span>{" "}
                  <span className="font-medium">+${bonus}</span>
                </div>
              ))}
          </div>
        </section>
      </div>
    </div>
  );
}
