"use client";

import { useCallback, useEffect, useState } from "react";
import { getFaRadar } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  BATTER_METRICS,
  PITCHER_METRICS,
  STATCAST_GLOSSARY,
  metricTooltip,
  type MetricKey,
} from "@/lib/statcastGlossary";
import type { FaRadarResponse, RadarPlayer, StatcastProfile } from "@/types";

type Role = "batter" | "pitcher";

const WINDOW_OPTIONS = [
  { value: 7, label: "近 7 天" },
  { value: 15, label: "近 15 天" },
  { value: 30, label: "近 30 天" },
];

/** Format a wOBA-scale number as .385 (leading zero dropped, baseball style). */
function woba(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const text = value.toFixed(3);
  return text.startsWith("0.") ? text.slice(1) : text;
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value}%`;
}

function plain(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(value);
}

/** Pull the display value for one metric out of a profile. */
function metricValue(key: MetricKey, profile: StatcastProfile): string {
  switch (key) {
    case "xwoba":
    case "xwoba_against":
      return woba(profile.xwoba);
    case "woba":
      return woba(profile.woba);
    case "barrel_rate":
    case "barrel_rate_against":
      return pct(profile.barrel_rate);
    case "hard_hit_rate":
    case "hard_hit_rate_against":
      return pct(profile.hard_hit_rate);
    case "avg_ev":
      return profile.avg_ev === null ? "—" : `${profile.avg_ev}`;
    case "whiff_rate":
      return pct(profile.whiff_rate);
    case "velo":
      return profile.avg_fastball_velo === null ? "—" : `${profile.avg_fastball_velo}`;
    case "pa":
      return plain(profile.pa);
    case "pitches":
      return plain(profile.pitches);
  }
}

/** The season-baseline counterpart, used to show the recent-vs-season gap. */
function seasonValue(key: MetricKey, profile: StatcastProfile | null): number | null {
  if (!profile) return null;
  switch (key) {
    case "barrel_rate":
    case "barrel_rate_against":
      return profile.barrel_rate;
    case "hard_hit_rate":
    case "hard_hit_rate_against":
      return profile.hard_hit_rate;
    case "whiff_rate":
      return profile.whiff_rate;
    case "velo":
      return profile.avg_fastball_velo;
    case "avg_ev":
      return profile.avg_ev;
    default:
      return null;
  }
}

function recentValue(key: MetricKey, profile: StatcastProfile): number | null {
  return seasonValue(key, profile);
}

function StatCell({
  metric,
  recent,
  season,
}: {
  metric: MetricKey;
  recent: StatcastProfile;
  season: StatcastProfile | null;
}) {
  const glossary = STATCAST_GLOSSARY[metric];
  const r = recentValue(metric, recent);
  const s = seasonValue(metric, season);
  const diff = r !== null && s !== null ? r - s : null;
  const meaningful = diff !== null && Math.abs(diff) >= 0.05;

  return (
    <div className="min-w-0" title={metricTooltip(metric)}>
      <div className="cursor-help text-[11px] uppercase tracking-wide text-gray-500 underline decoration-dotted decoration-gray-300 underline-offset-2">
        {glossary.label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-sm font-semibold text-gray-900 tabular-nums">
          {metricValue(metric, recent)}
        </span>
        {meaningful && (
          <span
            className={`text-[11px] tabular-nums ${
              diff > 0 ? "text-emerald-600" : "text-rose-600"
            }`}
          >
            {diff > 0 ? "+" : "-"}
            {Math.abs(diff).toFixed(1)}
          </span>
        )}
      </div>
    </div>
  );
}

function PlayerCard({ player, rank, role }: { player: RadarPlayer; rank: number; role: Role }) {
  const metrics = role === "batter" ? BATTER_METRICS : PITCHER_METRICS;

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
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
            FA (Free Agent)
          </span>
        )}
        <span
          className="ml-auto cursor-help rounded bg-indigo-600 px-2 py-0.5 text-xs font-semibold text-white tabular-nums"
          title={
            "雷達分數 Radar Score\n" +
            "由下方各項指標加總：絕對水準 + 相對於自己整季基準的進步幅度。\n" +
            "解讀：分數只用於排序候選人，不代表球員價值高低。"
          }
        >
          {player.score.toFixed(0)}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {metrics.map((metric) => (
          <StatCell key={metric} metric={metric} recent={player.recent} season={player.season} />
        ))}
      </div>

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

function InfoGuide({ role }: { role: Role }) {
  const metrics = role === "batter" ? BATTER_METRICS : PITCHER_METRICS;

  return (
    <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-gray-700">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-2 font-semibold text-blue-800">怎麼看這頁 How to Read</h3>
          <ul className="space-y-1 text-xs">
            <li>
              這頁<span className="font-medium">不是</span>近期成績排行榜，而是「底層數據」排行榜。
            </li>
            <li>
              成績會騙人（守備、球場、運氣），擊球品質不會。找的是
              <span className="font-medium">數據已經變好、但成績還沒反映</span>的球員。
            </li>
            <li>先看「成績落後預期」這類理由，那代表買進的時機還在。</li>
            <li>
              樣本太小時比率數據會劇烈波動，請一併看 PA / 球數。
            </li>
          </ul>

          <h4 className="mb-1 mt-3 text-xs font-medium text-blue-700">資料來源 Data Source</h4>
          <ul className="space-y-0.5 text-xs text-gray-600">
            <li>Baseball Savant（Statcast 逐球資料），每日自動同步</li>
            <li>持有狀態來自 Yahoo 名冊，預設只顯示未被持有的球員</li>
          </ul>
        </div>

        <div>
          <h3 className="mb-2 font-semibold text-blue-800">
            指標說明 Metrics（{role === "batter" ? "打者" : "投手"}）
          </h3>
          <ul className="space-y-1.5 text-xs">
            {metrics.map((key) => {
              const g = STATCAST_GLOSSARY[key];
              return (
                <li key={key}>
                  <span className="font-medium">{g.label}</span>
                  <span className="text-gray-500"> — {g.meaning}</span>
                  <div className="text-gray-600">解讀：{g.how}</div>
                  {"benchmark" in g && g.benchmark && (
                    <div className="text-gray-400">參考值：{g.benchmark}</div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

export default function RadarPage() {
  const { user, loading: authLoading } = useAuth();
  const [role, setRole] = useState<Role>("batter");
  const [windowDays, setWindowDays] = useState(15);
  const [ownerFilter, setOwnerFilter] = useState<"fa" | "all">("fa");
  const [showGuide, setShowGuide] = useState(false);
  const [data, setData] = useState<FaRadarResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(
        await getFaRadar({
          role,
          windowDays,
          includeOwned: ownerFilter === "all",
          limit: 25,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "載入失敗");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [role, windowDays, ownerFilter]);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  if (authLoading) {
    return <div className="p-8 text-center text-gray-500">載入中...</div>;
  }
  if (!user) {
    return (
      <div className="mx-auto max-w-2xl p-8 text-center">
        <h1 className="mb-2 text-xl font-bold">進階數據雷達 Statcast Radar</h1>
        <p className="text-gray-600">請先登入以檢視。</p>
      </div>
    );
  }

  const selectClass =
    "rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500";

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-4">
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
          進階數據雷達 Statcast Radar
        </h1>
        <p className="mt-1 text-sm text-gray-600">
          依 Baseball Savant 逐球數據，找出近期底層數據優於帳面成績的球員。
        </p>
      </header>

      {/* Info Guide (collapsible) — same pattern as the player database page */}
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
        {showGuide && <InfoGuide role={role} />}
      </div>

      {/* Controls Row */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            className={selectClass}
            title="切換打者 / 投手，指標會跟著換成該角色適用的項目"
          >
            <option value="batter">打者 Batters</option>
            <option value="pitcher">投手 Pitchers</option>
          </select>

          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className={selectClass}
            title="統計區間：越短越靈敏但樣本越小，越長越穩定但反應慢"
          >
            {WINDOW_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <select
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value as "fa" | "all")}
            className={selectClass}
            title="是否把已被聯盟其他隊持有的球員一起列出"
          >
            <option value="fa">FA (Free Agent)</option>
            <option value="all">All Players 含已持有</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          {data && (
            <span className="text-sm text-gray-600">
              篩選結果 {data.total_candidates} 位球員
            </span>
          )}
          <button
            onClick={() => void load()}
            disabled={loading}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "載入中..." : "重新整理"}
          </button>
        </div>
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
              區間 {data.window.start} ~ {data.window.end}（{data.window.days} 天）
              {data.players.length > 0 && ` · 顯示前 ${data.players.length} 名`}
              {" · "}
              Statcast 已匯入 {data.coverage.days} 天
              {data.coverage.last_date && `（最新 ${data.coverage.last_date}）`}
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
        <p>
          資料來源：Baseball Savant（Statcast 逐球資料）+ MLB Stats API。每日自動同步。
          將游標移到指標名稱上可看說明。
        </p>
      </footer>
    </div>
  );
}
