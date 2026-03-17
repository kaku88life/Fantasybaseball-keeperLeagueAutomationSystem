"use client";

import React, { useState } from "react";
import useSWR from "swr";
import {
  getDraftStats,
  getFaabStats,
  getPositionPreference,
  getTradeStats,
} from "@/lib/api";
import type {
  DraftStatsResponse,
  DraftPick,
  FaabStatsResponse,
  PositionPreferenceResponse,
  TradeStatsResponse,
  TradeDetail,
} from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

const TABS = [
  { id: "draft", label: "選秀 Top 10" },
  { id: "faab", label: "FAAB 統計" },
  { id: "position", label: "位置偏好" },
  { id: "trade", label: "交易統計" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// Position category colors
const POS_COLORS: Record<string, string> = {
  SP: "bg-blue-100 text-blue-800",
  RP: "bg-cyan-100 text-cyan-800",
  OF: "bg-green-100 text-green-800",
  IF: "bg-amber-100 text-amber-800",
  C: "bg-purple-100 text-purple-800",
  DH: "bg-gray-100 text-gray-800",
  Unknown: "bg-gray-50 text-gray-500",
};

export default function AnalyticsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("draft");

  const { data: draftData, isLoading: draftLoading } = useSWR<DraftStatsResponse>(
    activeTab === "draft" ? "analytics-draft" : null,
    () => getDraftStats(),
  );

  const { data: faabData, isLoading: faabLoading } = useSWR<FaabStatsResponse>(
    activeTab === "faab" ? "analytics-faab" : null,
    () => getFaabStats(),
  );

  const { data: posData, isLoading: posLoading } = useSWR<PositionPreferenceResponse>(
    activeTab === "position" ? "analytics-position" : null,
    () => getPositionPreference(),
  );

  const { data: tradeData, isLoading: tradeLoading } = useSWR<TradeStatsResponse>(
    activeTab === "trade" ? "analytics-trade" : null,
    () => getTradeStats(),
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <h1 className="text-2xl font-bold text-gray-900">
        聯盟統計分析 League Analytics
      </h1>
      <p className="mt-1 text-sm text-gray-500">
        選秀花費習慣、FAAB 使用、位置偏好、交易活動
      </p>

      {/* Tab Navigation */}
      <div className="mb-5 mt-4 flex gap-1 overflow-x-auto border-b border-gray-200">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors ${
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

      {activeTab === "draft" && (
        draftLoading ? <LoadingSpinner /> : draftData ? <DraftStatsTab data={draftData} /> : <EmptyState />
      )}
      {activeTab === "faab" && (
        faabLoading ? <LoadingSpinner /> : faabData ? <FaabStatsTab data={faabData} /> : <EmptyState />
      )}
      {activeTab === "position" && (
        posLoading ? <LoadingSpinner /> : posData ? <PositionPreferenceTab data={posData} /> : <EmptyState />
      )}
      {activeTab === "trade" && (
        tradeLoading ? <LoadingSpinner /> : tradeData ? <TradeStatsTab data={tradeData} /> : <EmptyState />
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-8 text-center text-gray-500">
      尚無資料。Commissioner 需先透過 Yahoo API 抓取選秀資料。
    </div>
  );
}

// ========== Year Selector ==========

function YearSelector({
  years,
  selected,
  onChange,
}: {
  years: number[];
  selected: string;
  onChange: (y: string) => void;
}) {
  if (years.length <= 1) return null;
  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="text-xs font-medium text-gray-500">年度:</span>
      <div className="flex gap-1">
        {years.map((y) => (
          <button
            key={y}
            onClick={() => onChange(String(y))}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              selected === String(y)
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {y}
          </button>
        ))}
      </div>
    </div>
  );
}

// ========== Draft Stats (Top 10) ==========

function costBarColor(cost: number): string {
  if (cost >= 50) return "bg-indigo-600";
  if (cost >= 30) return "bg-indigo-500";
  if (cost >= 20) return "bg-indigo-400";
  if (cost >= 10) return "bg-indigo-300";
  return "bg-indigo-200";
}

function _categorize(position: string): string {
  if (!position) return "Unknown";
  const primary = position.split(",")[0].trim();
  if (primary === "C") return "C";
  if (["1B", "2B", "3B", "SS"].includes(primary)) return "IF";
  if (["LF", "CF", "RF", "OF"].includes(primary)) return "OF";
  if (primary === "SP") return "SP";
  if (primary === "RP") return "RP";
  if (["DH", "Util"].includes(primary)) return "DH";
  return "Unknown";
}

function DraftStatsTab({ data }: { data: DraftStatsResponse }) {
  const years = data.years;
  const [selectedYear, setSelectedYear] = useState(
    years.length > 0 ? String(years[years.length - 1]) : "",
  );
  const [sortKey, setSortKey] = useState<"top10_total" | "manager">("top10_total");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  // Global max for bar scaling
  let globalMax = 1;
  for (const teamData of Object.values(data.teams)) {
    const yd = teamData.yearly[selectedYear];
    if (yd) {
      for (const p of yd.top_picks) {
        if (p.cost > globalMax) globalMax = p.cost;
      }
    }
  }

  const sortedTeams = Object.entries(data.teams)
    .filter(([, td]) => td.yearly[selectedYear])
    .sort((a, b) => {
      if (sortKey === "manager") {
        return sortDir === "asc" ? a[0].localeCompare(b[0]) : b[0].localeCompare(a[0]);
      }
      const aVal = a[1].yearly[selectedYear]?.top10_total ?? 0;
      const bVal = b[1].yearly[selectedYear]?.top10_total ?? 0;
      return sortDir === "asc" ? aVal - bVal : bVal - aVal;
    });

  const handleSort = (key: typeof sortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("desc"); }
  };

  const arrow = (key: typeof sortKey) =>
    sortKey === key ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : " \u25BD";

  const summary = data.yearly_summary[selectedYear];

  return (
    <div>
      <YearSelector years={years} selected={selectedYear} onChange={setSelectedYear} />

      {summary && (
        <div className="mb-3 inline-flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700">
          <span className="font-semibold">聯盟最高:</span>
          <span>${summary.league_max.cost} {summary.league_max.player} ({summary.league_max.manager})</span>
        </div>
      )}

      <p className="mb-3 text-xs text-gray-500">
        每位 GM 選秀花費最高的前 10 筆。柱狀長度代表花費金額，點擊展開明細。
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th
                onClick={() => handleSort("manager")}
                className="cursor-pointer whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500 hover:text-gray-700"
              >
                經理{arrow("manager")}
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
                Top 10 花費分布
              </th>
              <th
                onClick={() => handleSort("top10_total")}
                className="cursor-pointer whitespace-nowrap px-3 py-2 text-right text-xs font-medium uppercase text-gray-500 hover:text-gray-700"
              >
                Top 10 小計{arrow("top10_total")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {sortedTeams.map(([mgr, teamData]) => {
              const yd = teamData.yearly[selectedYear];
              if (!yd) return null;
              const isExpanded = expandedTeam === mgr;
              return (
                <React.Fragment key={mgr}>
                  <tr
                    className="cursor-pointer hover:bg-gray-50"
                    onClick={() => setExpandedTeam(isExpanded ? null : mgr)}
                  >
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium text-gray-900">
                      <span className="mr-1 text-xs text-gray-400">
                        {isExpanded ? "\u25BC" : "\u25B6"}
                      </span>
                      {mgr}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-0.5">
                        {yd.top_picks.map((p: DraftPick, i: number) => (
                          <div
                            key={i}
                            title={`${p.player} $${p.cost} (Rd ${p.round})`}
                            className={`h-6 rounded-sm ${costBarColor(p.cost)} transition-all hover:opacity-80`}
                            style={{ width: `${Math.max((p.cost / globalMax) * 100, 3)}%` }}
                          >
                            {p.cost >= 15 && (
                              <span className="flex h-full items-center justify-center text-[10px] font-bold text-white">
                                ${p.cost}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums font-semibold text-indigo-700">
                      ${yd.top10_total}
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr>
                      <td colSpan={3} className="bg-gray-50 px-4 py-3">
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-gray-400">
                                <th className="w-8 pb-1 pr-2">#</th>
                                <th className="pb-1 pr-2">球員</th>
                                <th className="pb-1 pr-2">位置</th>
                                <th className="pb-1 pr-2 text-right">花費</th>
                                <th className="pb-1 pr-2 text-right">Round</th>
                                <th className="pb-1">占比</th>
                              </tr>
                            </thead>
                            <tbody>
                              {yd.top_picks.map((p: DraftPick, i: number) => (
                                <tr key={i} className="border-t border-gray-100">
                                  <td className="py-1 pr-2 tabular-nums text-gray-400">{i + 1}</td>
                                  <td className="py-1 pr-2 font-medium text-gray-800">{p.player}</td>
                                  <td className="py-1 pr-2">
                                    <span
                                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${POS_COLORS[_categorize(p.position)] ?? POS_COLORS.Unknown}`}
                                    >
                                      {p.position || "?"}
                                    </span>
                                  </td>
                                  <td className="py-1 pr-2 text-right tabular-nums font-semibold">${p.cost}</td>
                                  <td className="py-1 pr-2 text-right tabular-nums text-gray-500">Rd {p.round}</td>
                                  <td className="py-1">
                                    <div className="flex items-center gap-1">
                                      <div className="h-2 rounded-full bg-gray-200" style={{ width: "60px" }}>
                                        <div
                                          className={`h-2 rounded-full ${costBarColor(p.cost)}`}
                                          style={{ width: `${(p.cost / globalMax) * 100}%` }}
                                        />
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div className="mt-2 text-xs text-gray-400">
                          全部 {yd.players_drafted} 筆選秀，總花費 ${yd.total_spent}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ========== FAAB Stats ==========

function FaabStatsTab({ data }: { data: FaabStatsResponse }) {
  const years = data.years;
  const [selectedYear, setSelectedYear] = useState(
    years.length > 0 ? String(years[years.length - 1]) : "",
  );
  const [sortKey, setSortKey] = useState<"total_faab_spent" | "remaining_pct" | "num_pickups" | "max_bid">("total_faab_spent");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sortedTeams = Object.entries(data.teams)
    .filter(([, td]) => td.yearly[selectedYear])
    .sort((a, b) => {
      const aVal = a[1].yearly[selectedYear]?.[sortKey] ?? 0;
      const bVal = b[1].yearly[selectedYear]?.[sortKey] ?? 0;
      return sortDir === "asc" ? aVal - bVal : bVal - aVal;
    });

  const handleSort = (key: typeof sortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("desc"); }
  };

  const arrow = (key: typeof sortKey) =>
    sortKey === key ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : " \u25BD";

  const summary = data.yearly_summary[selectedYear];

  return (
    <div>
      <YearSelector years={years} selected={selectedYear} onChange={setSelectedYear} />

      {summary && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryCard label="FAAB 年度預算" value={`$${summary.faab_budget}`} />
          <SummaryCard label="聯盟總 FAAB 花費" value={`$${summary.total_league_faab_spent}`} />
          <SummaryCard label="隊伍平均花費" value={`$${summary.avg_team_faab_spent}`} />
          <SummaryCard label="參與隊伍" value={`${summary.team_count}`} />
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">經理</th>
              <th onClick={() => handleSort("total_faab_spent")} className="cursor-pointer px-3 py-2 text-right text-xs font-medium uppercase text-gray-500 hover:text-gray-700">
                花費{arrow("total_faab_spent")}
              </th>
              <th onClick={() => handleSort("remaining_pct")} className="cursor-pointer px-3 py-2 text-right text-xs font-medium uppercase text-gray-500 hover:text-gray-700">
                剩餘%{arrow("remaining_pct")}
              </th>
              <th onClick={() => handleSort("num_pickups")} className="cursor-pointer px-3 py-2 text-right text-xs font-medium uppercase text-gray-500 hover:text-gray-700">
                撿人次數{arrow("num_pickups")}
              </th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">均價</th>
              <th onClick={() => handleSort("max_bid")} className="cursor-pointer px-3 py-2 text-right text-xs font-medium uppercase text-gray-500 hover:text-gray-700">
                最高出價{arrow("max_bid")}
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">最高球員</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {sortedTeams.map(([mgr, teamData]) => {
              const yd = teamData.yearly[selectedYear];
              if (!yd) return null;
              return (
                <tr key={mgr} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-3 py-2 font-medium text-gray-900">{mgr}</td>
                  <td className="px-3 py-2 text-right tabular-nums">${yd.total_faab_spent}</td>
                  <td className={`px-3 py-2 text-right tabular-nums ${yd.remaining_pct < 10 ? "font-medium text-red-600" : "text-gray-500"}`}>
                    {yd.remaining_pct}%
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-500">{yd.num_pickups}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-500">${yd.avg_bid}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium">${yd.max_bid}</td>
                  <td className="max-w-[150px] truncate px-3 py-2 text-gray-500" title={yd.max_bid_player}>
                    {yd.max_bid_player}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ========== Position Preference ==========

function PositionPreferenceTab({ data }: { data: PositionPreferenceResponse }) {
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);
  const years = data.years;
  const [selectedYear, setSelectedYear] = useState(
    years.length > 0 ? String(years[years.length - 1]) : "",
  );
  const posCategories = Object.keys(data.league_position_breakdown).sort();

  return (
    <div>
      <YearSelector years={years} selected={selectedYear} onChange={setSelectedYear} />

      {/* League Summary */}
      <div className="mb-4">
        <h3 className="mb-2 text-sm font-semibold text-gray-700">
          聯盟整體 $20+ 選秀位置分布
        </h3>
        <div className="flex flex-wrap gap-2">
          {posCategories.map((pos) => (
            <span
              key={pos}
              className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium ${POS_COLORS[pos] ?? POS_COLORS.Unknown}`}
            >
              {pos}: {data.league_position_breakdown[pos]}
            </span>
          ))}
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-1 text-sm font-medium text-indigo-700">
            Total: {Object.values(data.league_position_breakdown).reduce((a, b) => a + b, 0)}
          </span>
        </div>
      </div>

      {/* Per-team */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">經理</th>
              {posCategories.map((pos) => (
                <th key={pos} className="px-3 py-2 text-center text-xs font-medium uppercase text-gray-500">{pos}</th>
              ))}
              <th className="px-3 py-2 text-center text-xs font-medium uppercase text-gray-500">Total</th>
              <th className="px-3 py-2 text-center text-xs font-medium uppercase text-gray-500">Spent</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {Object.entries(data.teams)
              .sort((a, b) => {
                const aTotal = Object.values(a[1].career_position_breakdown).reduce((s, v) => s + v, 0);
                const bTotal = Object.values(b[1].career_position_breakdown).reduce((s, v) => s + v, 0);
                return bTotal - aTotal;
              })
              .map(([mgr, teamData]) => {
                const totalPicks = Object.values(teamData.career_position_breakdown).reduce((s, v) => s + v, 0);
                const totalSpent = Object.values(teamData.yearly).reduce((s, yd) => s + yd.total_spent, 0);
                const isExpanded = expandedTeam === mgr;

                return (
                  <React.Fragment key={mgr}>
                    <tr className="cursor-pointer hover:bg-gray-50" onClick={() => setExpandedTeam(isExpanded ? null : mgr)}>
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-gray-900">
                        <span className="mr-1 text-xs text-gray-400">{isExpanded ? "\u25BC" : "\u25B6"}</span>
                        {mgr}
                      </td>
                      {posCategories.map((pos) => (
                        <td key={pos} className="px-3 py-2 text-center tabular-nums">
                          {teamData.career_position_breakdown[pos] ? (
                            <span className={`inline-block min-w-[24px] rounded px-1.5 py-0.5 text-xs font-medium ${POS_COLORS[pos] ?? POS_COLORS.Unknown}`}>
                              {teamData.career_position_breakdown[pos]}
                            </span>
                          ) : (
                            <span className="text-gray-200">-</span>
                          )}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-center tabular-nums font-semibold">{totalPicks}</td>
                      <td className="px-3 py-2 text-center tabular-nums font-medium">${totalSpent}</td>
                    </tr>

                    {isExpanded && (
                      <tr>
                        <td colSpan={posCategories.length + 3} className="bg-gray-50 px-6 py-3">
                          {years.map((y) => {
                            const yd = teamData.yearly[String(y)];
                            if (!yd) return null;
                            return (
                              <div key={y} className="mb-2">
                                <h4 className="mb-1 text-xs font-semibold text-gray-600">{y}</h4>
                                <div className="flex flex-wrap gap-1.5">
                                  {yd.picks
                                    .sort((a, b) => b.cost - a.cost)
                                    .map((p, i) => (
                                      <span
                                        key={i}
                                        className={`inline-flex items-center rounded px-2 py-0.5 text-xs ${POS_COLORS[p.pos_category] ?? POS_COLORS.Unknown}`}
                                      >
                                        {p.player} ${p.cost}
                                        <span className="ml-1 text-[10px] opacity-70">({p.position})</span>
                                      </span>
                                    ))}
                                </div>
                              </div>
                            );
                          })}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ========== Trade Stats ==========

function TradeStatsTab({ data }: { data: TradeStatsResponse }) {
  const years = data.years;
  const [selectedYear, setSelectedYear] = useState(
    years.length > 0 ? String(years[years.length - 1]) : "",
  );
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  const teamsWithTrades = Object.entries(data.teams)
    .filter(([, td]) => td.yearly[selectedYear])
    .sort((a, b) => {
      const aCount = a[1].yearly[selectedYear]?.trade_count ?? 0;
      const bCount = b[1].yearly[selectedYear]?.trade_count ?? 0;
      return bCount - aCount;
    });

  const summary = data.yearly_summary[selectedYear];
  const maxTradeCount = teamsWithTrades.length > 0
    ? Math.max(...teamsWithTrades.map(([, td]) => td.yearly[selectedYear]?.trade_count ?? 0))
    : 1;

  return (
    <div>
      <YearSelector years={years} selected={selectedYear} onChange={setSelectedYear} />

      {summary && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <SummaryCard label="交易總筆數" value={`${summary.total_trades}`} />
          <SummaryCard label="參與交易隊伍" value={`${summary.team_count}`} />
          <SummaryCard label="資料年份" value={selectedYear} />
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">經理</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">交易次數</th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">活躍度</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">送出球員</th>
              <th className="px-3 py-2 text-right text-xs font-medium uppercase text-gray-500">獲得球員</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {teamsWithTrades.map(([mgr, teamData]) => {
              const yd = teamData.yearly[selectedYear];
              if (!yd) return null;
              const isExpanded = expandedTeam === mgr;
              return (
                <React.Fragment key={mgr}>
                  <tr
                    className="cursor-pointer hover:bg-gray-50"
                    onClick={() => setExpandedTeam(isExpanded ? null : mgr)}
                  >
                    <td className="whitespace-nowrap px-3 py-2 font-medium text-gray-900">
                      <span className="mr-1 text-xs text-gray-400">{isExpanded ? "\u25BC" : "\u25B6"}</span>
                      {mgr}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold text-indigo-700">
                      {yd.trade_count}
                    </td>
                    <td className="px-3 py-2">
                      <div className="h-3 w-32 rounded-full bg-gray-200">
                        <div
                          className="h-3 rounded-full bg-indigo-500"
                          style={{ width: `${(yd.trade_count / maxTradeCount) * 100}%` }}
                        />
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-gray-500">
                      {yd.players_sent.length}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-gray-500">
                      {yd.players_received.length}
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr>
                      <td colSpan={5} className="bg-gray-50 px-4 py-3">
                        <div className="space-y-2">
                          {yd.trades.map((trade: TradeDetail, i: number) => {
                            const date = trade.timestamp
                              ? new Date(Number(trade.timestamp) * 1000).toLocaleDateString("zh-TW")
                              : "";
                            return (
                              <div key={i} className="rounded-md border border-gray-200 bg-white p-3">
                                <div className="mb-1.5 flex items-center gap-2 text-xs text-gray-500">
                                  <span className="font-medium text-gray-700">交易 #{i + 1}</span>
                                  <span>vs {trade.partner}</span>
                                  {date && <span className="text-gray-400">{date}</span>}
                                </div>
                                <div className="grid grid-cols-2 gap-4 text-xs">
                                  <div>
                                    <span className="mb-1 block font-medium text-red-600">送出:</span>
                                    <div className="flex flex-wrap gap-1">
                                      {trade.sent.map((name, j) => (
                                        <span key={j} className="rounded bg-red-50 px-1.5 py-0.5 text-red-700">
                                          {name}
                                        </span>
                                      ))}
                                      {trade.sent.length === 0 && <span className="text-gray-300">-</span>}
                                    </div>
                                  </div>
                                  <div>
                                    <span className="mb-1 block font-medium text-green-600">獲得:</span>
                                    <div className="flex flex-wrap gap-1">
                                      {trade.received.map((name, j) => (
                                        <span key={j} className="rounded bg-green-50 px-1.5 py-0.5 text-green-700">
                                          {name}
                                        </span>
                                      ))}
                                      {trade.received.length === 0 && <span className="text-gray-300">-</span>}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            {teamsWithTrades.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-gray-400">
                  {selectedYear} 年無交易紀錄
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ========== Shared ==========

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-lg font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 truncate text-xs text-gray-500">{sub}</p>}
    </div>
  );
}
