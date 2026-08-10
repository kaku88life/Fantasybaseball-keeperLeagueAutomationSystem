"use client";

import { useCallback, useEffect, useState } from "react";
import { getFaRadar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { FaRadarResponse, RadarPlayer, StatcastProfile } from "@/types";

type Role = "batter" | "pitcher";

const WINDOW_OPTIONS = [7, 15, 30];

/** Format a rate stat, showing an em dash when the sample is missing. */
function rate(value: number | null, suffix = "%"): string {
  return value === null || value === undefined ? "—" : `${value}${suffix}`;
}

/** Format a wOBA-scale number as .385 (leading zero dropped, baseball style). */
function woba(value: number | null): string {
  if (value === null || value === undefined) return "—";
  const text = value.toFixed(3);
  return text.startsWith("0.") ? text.slice(1) : text;
}

function delta(recent: number | null, season: number | null): string | null {
  if (recent === null || season === null) return null;
  const diff = recent - season;
  if (Math.abs(diff) < 0.05) return null;
  return `${diff > 0 ? "+" : ""}${diff.toFixed(1)}`;
}

function StatCell({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string | null;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-sm font-semibold text-gray-900 tabular-nums">{value}</span>
        {hint && (
          <span
            className={`text-[11px] tabular-nums ${
              hint.startsWith("+") ? "text-emerald-600" : "text-rose-600"
            }`}
          >
            {hint}
          </span>
        )}
      </div>
    </div>
  );
}

function BatterStats({ recent, season }: { recent: StatcastProfile; season: StatcastProfile | null }) {
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      <StatCell label="xwOBA" value={woba(recent.xwoba)} />
      <StatCell label="wOBA" value={woba(recent.woba)} />
      <StatCell
        label="Barrel%"
        value={rate(recent.barrel_rate)}
        hint={delta(recent.barrel_rate, season?.barrel_rate ?? null)}
      />
      <StatCell
        label="Hard-Hit%"
        value={rate(recent.hard_hit_rate)}
        hint={delta(recent.hard_hit_rate, season?.hard_hit_rate ?? null)}
      />
      <StatCell label="平均初速" value={rate(recent.avg_ev, "")} />
      <StatCell label="PA" value={String(recent.pa)} />
    </div>
  );
}

function PitcherStats({ recent, season }: { recent: StatcastProfile; season: StatcastProfile | null }) {
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      <StatCell label="被打 xwOBA" value={woba(recent.xwoba)} />
      <StatCell
        label="Whiff%"
        value={rate(recent.whiff_rate)}
        hint={delta(recent.whiff_rate, season?.whiff_rate ?? null)}
      />
      <StatCell
        label="速球均速"
        value={rate(recent.avg_fastball_velo, "")}
        hint={delta(recent.avg_fastball_velo, season?.avg_fastball_velo ?? null)}
      />
      <StatCell label="Barrel%(被)" value={rate(recent.barrel_rate)} />
      <StatCell label="Hard-Hit%(被)" value={rate(recent.hard_hit_rate)} />
      <StatCell label="球數" value={String(recent.pitches)} />
    </div>
  );
}

function PlayerCard({ player, rank, role }: { player: RadarPlayer; rank: number; role: Role }) {
  return (
    <li className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-mono text-gray-400">#{rank}</span>
        <span className="text-base font-semibold text-gray-900">{player.name}</span>
        {player.owned ? (
          <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-700">
            {player.owner_team || player.owner_manager || "已被持有"}
          </span>
        ) : (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">FA</span>
        )}
        <span className="ml-auto rounded bg-indigo-600 px-2 py-0.5 text-xs font-semibold text-white tabular-nums">
          {player.score.toFixed(0)}
        </span>
      </div>

      {role === "batter" ? (
        <BatterStats recent={player.recent} season={player.season} />
      ) : (
        <PitcherStats recent={player.recent} season={player.season} />
      )}

      {player.reasons.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-gray-100 pt-3">
          {player.reasons.map((reason) => (
            <li key={reason} className="text-xs text-gray-600">
              • {reason}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function RadarPage() {
  const { user, loading: authLoading } = useAuth();
  const [role, setRole] = useState<Role>("batter");
  const [windowDays, setWindowDays] = useState(15);
  const [includeOwned, setIncludeOwned] = useState(false);
  const [data, setData] = useState<FaRadarResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getFaRadar({ role, windowDays, includeOwned, limit: 25 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "載入失敗");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [role, windowDays, includeOwned]);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  if (authLoading) {
    return <div className="p-8 text-center text-gray-500">載入中...</div>;
  }
  if (!user) {
    return (
      <div className="mx-auto max-w-2xl p-8 text-center">
        <h1 className="mb-2 text-xl font-bold">進階數據雷達</h1>
        <p className="text-gray-600">請先登入以檢視。</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
          進階數據雷達 Statcast Radar
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          依 Baseball Savant 逐球數據，找出近期「底層數據」優於帳面成績的球員。
          排名不看短期成績，看擊球品質與制球宰制力。
        </p>
      </header>

      {/* Controls */}
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
        <div className="flex rounded-md border border-gray-300 bg-white">
          {(["batter", "pitcher"] as Role[]).map((r) => (
            <button
              key={r}
              onClick={() => setRole(r)}
              className={`px-3 py-1.5 text-sm ${
                role === r ? "bg-indigo-600 text-white" : "text-gray-700 hover:bg-gray-50"
              } ${r === "batter" ? "rounded-l-md" : "rounded-r-md"}`}
            >
              {r === "batter" ? "打者" : "投手"}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <span className="text-sm text-gray-600">區間</span>
          {WINDOW_OPTIONS.map((days) => (
            <button
              key={days}
              onClick={() => setWindowDays(days)}
              className={`rounded px-2 py-1 text-sm ${
                windowDays === days
                  ? "bg-gray-900 text-white"
                  : "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50"
              }`}
            >
              {days}天
            </button>
          ))}
        </div>

        <label className="flex items-center gap-1.5 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={includeOwned}
            onChange={(e) => setIncludeOwned(e.target.checked)}
            className="rounded border-gray-300"
          />
          含已持有球員
        </label>

        <button
          onClick={() => void load()}
          disabled={loading}
          className="ml-auto rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "載入中..." : "重新整理"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="mb-4 space-y-1 text-xs text-gray-500">
            <div>
              區間 {data.window.start} ~ {data.window.end}（{data.window.days} 天）·
              符合門檻 {data.total_candidates} 人，顯示前 {data.players.length} 名
            </div>
            <div>
              Statcast 已匯入 {data.coverage.days} 天
              {data.coverage.last_date && `（最新 ${data.coverage.last_date}）`}
              {data.ownership.players > 0 && ` · 持有名單 ${data.ownership.players} 人`}
            </div>
            {data.notes.map((note) => (
              <div key={note} className="text-amber-700">
                ⚠ {note}
              </div>
            ))}
          </div>

          {data.players.length === 0 ? (
            <div className="rounded border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
              這個區間沒有符合條件的球員。試著拉長區間，或確認 Statcast 資料已同步。
            </div>
          ) : (
            <ul className="space-y-3">
              {data.players.map((player, idx) => (
                <PlayerCard key={player.player_id} player={player} rank={idx + 1} role={role} />
              ))}
            </ul>
          )}
        </>
      )}

      <footer className="mt-8 border-t border-gray-200 pt-4 text-xs text-gray-500">
        <p>資料來源：Baseball Savant（Statcast 逐球資料）+ MLB Stats API。每日自動同步。</p>
        <p className="mt-1">
          Barrel% / Hard-Hit% 以擊球事件為分母；xwOBA 為預期加權上壘率。
          綠色為較整季進步、紅色為退步。
        </p>
      </footer>
    </div>
  );
}
