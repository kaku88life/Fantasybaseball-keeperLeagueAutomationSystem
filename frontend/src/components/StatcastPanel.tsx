"use client";

import { useEffect, useState } from "react";
import { getPlayerStatcast } from "@/lib/api";
import { STATCAST_GLOSSARY, metricTooltip, type MetricKey } from "@/lib/statcastGlossary";
import type { PlayerStatcastResponse, StatcastProfile } from "@/types";

interface StatcastPanelProps {
  mlbId: number;
  /** Primary position, used to decide whether to show hitting or pitching metrics. */
  position: string;
}

const WINDOW_DAYS = 15;

/** Position tokens that mean "treat this player as a pitcher". */
const PITCHER_TOKENS = new Set(["P", "SP", "RP", "LHP", "RHP", "TWP"]);

function isPitcher(position: string): boolean {
  return (position || "")
    .replace(/\//g, ",")
    .split(",")
    .map((token) => token.trim().toUpperCase())
    .some((token) => PITCHER_TOKENS.has(token));
}

function woba(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const text = value.toFixed(3);
  return text.startsWith("0.") ? text.slice(1) : text;
}

function num(value: number | null | undefined, suffix = ""): string {
  return value === null || value === undefined ? "—" : `${value}${suffix}`;
}

/**
 * Format a gap. wOBA-scale metrics read as .037; counting/rate metrics as 0.8,
 * because ".800" on a mph or percentage row is badly misleading.
 */
function formatDiff(diff: number, scale: "woba" | "plain"): string {
  const sign = diff > 0 ? "+" : "-";
  const magnitude = Math.abs(diff);
  if (scale === "woba") {
    return `${sign}${magnitude.toFixed(3).replace(/^0\./, ".")}`;
  }
  return `${sign}${magnitude.toFixed(1)}`;
}

/**
 * One metric with its recent value, season value, and the gap between them.
 * `higherIsBetter` flips the colour so "lower is good" metrics read correctly.
 */
function MetricRow({
  metric,
  recent,
  season,
  format,
  higherIsBetter = true,
  scale = "plain",
}: {
  metric: MetricKey;
  recent: number | null | undefined;
  season: number | null | undefined;
  format: (v: number | null | undefined) => string;
  higherIsBetter?: boolean;
  scale?: "woba" | "plain";
}) {
  const glossary = STATCAST_GLOSSARY[metric];
  const hasBoth = recent !== null && recent !== undefined && season !== null && season !== undefined;
  const diff = hasBoth ? recent - season : null;
  // A wOBA move of .001 matters; 0.05 mph does not.
  const threshold = scale === "woba" ? 0.001 : 0.05;
  const meaningful = diff !== null && Math.abs(diff) >= threshold;
  const improving = meaningful ? (higherIsBetter ? diff > 0 : diff < 0) : false;

  return (
    <tr className="border-t border-gray-100">
      <td className="px-2 py-1.5" title={metricTooltip(metric)}>
        <div className="cursor-help text-xs font-medium text-gray-800 underline decoration-dotted decoration-gray-300 underline-offset-2">
          {glossary.label}
        </div>
        <div className="text-[10px] text-gray-400">{glossary.meaning}</div>
      </td>
      <td className="px-2 py-1.5 text-right text-sm font-semibold text-gray-900 tabular-nums">
        {format(recent)}
      </td>
      <td className="px-2 py-1.5 text-right text-sm text-gray-500 tabular-nums">
        {format(season)}
      </td>
      <td className="px-2 py-1.5 text-right text-xs tabular-nums">
        {meaningful ? (
          <span className={improving ? "text-emerald-600" : "text-rose-600"}>
            {formatDiff(diff, scale)}
          </span>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
    </tr>
  );
}

function ProfileTable({
  recent,
  season,
  pitcher,
}: {
  recent: StatcastProfile | null;
  season: StatcastProfile | null;
  pitcher: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[380px]">
        <thead className="bg-gray-50 text-[10px] text-gray-500">
          <tr>
            <th className="px-2 py-1.5 text-left">指標</th>
            <th className="px-2 py-1.5 text-right">近 {WINDOW_DAYS} 天</th>
            <th className="px-2 py-1.5 text-right">本季</th>
            <th className="px-2 py-1.5 text-right">差異</th>
          </tr>
        </thead>
        <tbody>
          {pitcher ? (
            <>
              <MetricRow
                metric="xwoba_against"
                recent={recent?.xwoba}
                season={season?.xwoba}
                format={woba}
                scale="woba"
                higherIsBetter={false}
              />
              <MetricRow
                metric="whiff_rate"
                recent={recent?.whiff_rate}
                season={season?.whiff_rate}
                format={(v) => num(v, "%")}
              />
              <MetricRow
                metric="velo"
                recent={recent?.avg_fastball_velo}
                season={season?.avg_fastball_velo}
                format={(v) => num(v, " mph")}
              />
              <MetricRow
                metric="barrel_rate_against"
                recent={recent?.barrel_rate}
                season={season?.barrel_rate}
                format={(v) => num(v, "%")}
                higherIsBetter={false}
              />
              <MetricRow
                metric="hard_hit_rate_against"
                recent={recent?.hard_hit_rate}
                season={season?.hard_hit_rate}
                format={(v) => num(v, "%")}
                higherIsBetter={false}
              />
            </>
          ) : (
            <>
              <MetricRow
                metric="xwoba"
                recent={recent?.xwoba}
                season={season?.xwoba}
                format={woba}
                scale="woba"
              />
              <MetricRow
                metric="woba"
                recent={recent?.woba}
                season={season?.woba}
                format={woba}
                scale="woba"
              />
              <MetricRow
                metric="barrel_rate"
                recent={recent?.barrel_rate}
                season={season?.barrel_rate}
                format={(v) => num(v, "%")}
              />
              <MetricRow
                metric="hard_hit_rate"
                recent={recent?.hard_hit_rate}
                season={season?.hard_hit_rate}
                format={(v) => num(v, "%")}
              />
              <MetricRow
                metric="avg_ev"
                recent={recent?.avg_ev}
                season={season?.avg_ev}
                format={(v) => num(v, " mph")}
              />
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function StatcastPanel({ mlbId, position }: StatcastPanelProps) {
  const pitcher = isPitcher(position);
  const [data, setData] = useState<PlayerStatcastResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!mlbId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    getPlayerStatcast(mlbId, {
      role: pitcher ? "pitcher" : "batter",
      windowDays: WINDOW_DAYS,
    })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "載入失敗");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mlbId, pitcher]);

  if (!mlbId) return null;

  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-gray-700">
        進階數據 Statcast
        <span className="ml-2 text-xs font-normal text-gray-400">
          {pitcher ? "投手視角" : "打者視角"}
        </span>
      </h4>

      {loading && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center text-xs text-gray-500">
          載入中...
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
          進階數據載入失敗：{error}
        </div>
      )}

      {!loading && !error && data && !data.recent && !data.season && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center text-xs text-gray-500">
          這名球員在已匯入的區間內沒有 Statcast 紀錄
          <div className="mt-1 text-[10px] text-gray-400">
            （小聯盟球員與尚未出賽者不會有資料）
          </div>
        </div>
      )}

      {!loading && !error && data && (data.recent || data.season) && (
        <>
          <ProfileTable recent={data.recent} season={data.season} pitcher={pitcher} />
          <p className="mt-2 text-[10px] text-gray-400">
            區間 {data.window.start} ~ {data.window.end}。綠色代表較本季進步、紅色代表退步。
            將游標移到指標名稱上可看說明。資料來源：Baseball Savant。
          </p>
        </>
      )}
    </div>
  );
}
