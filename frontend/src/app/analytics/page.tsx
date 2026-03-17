"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import useSWR from "swr";
import {
  getDraftStats,
  getFaabStats,
  getPositionPreference,
  getTradeStats,
  getSalaryRankings,
  getContractValues,
  getLeagueAnalyticsSummary,
} from "@/lib/api";
import type {
  DraftStatsResponse,
  DraftPick,
  FaabStatsResponse,
  PositionPreferenceResponse,
  TradeStatsResponse,
  TradeDetail,
  SalaryRankingsResponse,
  SalaryRankingEntry,
  ContractValuesResponse,
  ContractValue,
  LeagueSummaryResponse,
} from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import AuthGate from "@/components/AuthGate";

const TABS = [
  { id: "salary", label: "薪資排行" },
  { id: "contract", label: "合約總值" },
  { id: "draft", label: "選秀 Top 10" },
  { id: "faab", label: "FAAB" },
  { id: "position", label: "位置偏好" },
  { id: "trade", label: "交易" },
  { id: "summary", label: "總覽" },
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

// Contract type badge colors
const CT_COLORS: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-700",
  B: "bg-blue-100 text-blue-700",
  O: "bg-gray-100 text-gray-600",
  R: "bg-purple-100 text-purple-700",
  FA: "bg-gray-50 text-gray-500",
};
function contractBadgeColor(ct: string): string {
  if (ct.startsWith("N")) return "bg-amber-100 text-amber-700";
  return CT_COLORS[ct] ?? "bg-gray-100 text-gray-600";
}

// ========== Scrollable Tab Bar with hover arrows ==========

function ScrollableTabs({
  activeTab,
  onChange,
}: {
  activeTab: TabId;
  onChange: (t: TabId) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const [isHovering, setIsHovering] = useState(false);

  const checkScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 2);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 2);
  }, []);

  useEffect(() => {
    checkScroll();
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", checkScroll, { passive: true });
    window.addEventListener("resize", checkScroll);
    return () => {
      el.removeEventListener("scroll", checkScroll);
      window.removeEventListener("resize", checkScroll);
    };
  }, [checkScroll]);

  // Scroll active tab into view on mount
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const activeBtn = el.querySelector("[data-active='true']") as HTMLElement;
    if (activeBtn) {
      activeBtn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
  }, [activeTab]);

  const scroll = (dir: "left" | "right") => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollBy({ left: dir === "left" ? -120 : 120, behavior: "smooth" });
  };

  return (
    <div
      className="relative mb-4 mt-3"
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      {/* Left arrow */}
      {canScrollLeft && (
        <button
          onClick={() => scroll("left")}
          className={`absolute left-0 top-0 z-10 flex h-full w-7 items-center justify-center bg-gradient-to-r from-white via-white/90 to-transparent text-gray-400 transition-opacity hover:text-gray-600 ${
            isHovering ? "opacity-100" : "opacity-0 sm:opacity-0"
          } pointer-events-auto`}
          style={{ opacity: isHovering || canScrollLeft ? undefined : 0 }}
          aria-label="Scroll left"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Right arrow */}
      {canScrollRight && (
        <button
          onClick={() => scroll("right")}
          className={`absolute right-0 top-0 z-10 flex h-full w-7 items-center justify-center bg-gradient-to-l from-white via-white/90 to-transparent text-gray-400 transition-opacity hover:text-gray-600 ${
            isHovering ? "opacity-100" : "opacity-0 sm:opacity-0"
          } pointer-events-auto`}
          style={{ opacity: isHovering || canScrollRight ? undefined : 0 }}
          aria-label="Scroll right"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}

      {/* Tab strip */}
      <div
        ref={scrollRef}
        className="flex gap-0.5 overflow-x-auto border-b border-gray-200 scrollbar-none"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            data-active={activeTab === tab.id}
            onClick={() => onChange(tab.id)}
            className={`relative shrink-0 whitespace-nowrap px-3 py-2 text-xs font-medium transition-colors sm:px-4 sm:text-sm ${
              activeTab === tab.id
                ? "text-indigo-600"
                : "text-gray-400 hover:text-gray-600"
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 bg-indigo-600" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <AuthGate>
      <AnalyticsContent />
    </AuthGate>
  );
}

function AnalyticsContent() {
  const [activeTab, setActiveTab] = useState<TabId>("salary");

  const { data: salaryData, isLoading: salaryLoading } = useSWR<SalaryRankingsResponse>(
    activeTab === "salary" ? "analytics-salary" : null,
    () => getSalaryRankings(),
  );
  const { data: contractData, isLoading: contractLoading } = useSWR<ContractValuesResponse>(
    activeTab === "contract" ? "analytics-contract" : null,
    () => getContractValues(),
  );
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
  const { data: summaryData, isLoading: summaryLoading } = useSWR<LeagueSummaryResponse>(
    activeTab === "summary" ? "analytics-summary" : null,
    () => getLeagueAnalyticsSummary(),
  );

  return (
    <div className="mx-auto max-w-7xl px-3 py-4 sm:px-4 sm:py-6">
      <h1 className="text-lg font-bold text-gray-900 sm:text-2xl">
        聯盟統計分析
      </h1>
      <p className="mt-0.5 text-xs text-gray-400">
        歷史薪資 / 合約追蹤 / 選秀花費 / FAAB / 交易活動
      </p>

      <ScrollableTabs activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === "salary" && (
        salaryLoading ? <LoadingSpinner /> : salaryData ? <SalaryRankingsTab data={salaryData} /> : <EmptyState />
      )}
      {activeTab === "contract" && (
        contractLoading ? <LoadingSpinner /> : contractData ? <ContractValuesTab data={contractData} /> : <EmptyState />
      )}
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
      {activeTab === "summary" && (
        summaryLoading ? <LoadingSpinner /> : summaryData ? <SummaryTab data={summaryData} /> : <EmptyState />
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center text-sm text-gray-400">
      尚無資料
    </div>
  );
}

// ========== Year Selector (compact) ==========

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
    <div className="mb-2 flex items-center gap-1.5">
      <span className="text-[10px] font-medium text-gray-400 sm:text-xs">年度</span>
      <div className="flex gap-0.5">
        {years.map((y) => (
          <button
            key={y}
            onClick={() => onChange(String(y))}
            className={`rounded px-2 py-0.5 text-[11px] font-medium transition-colors sm:px-3 sm:py-1 sm:text-xs ${
              selected === String(y)
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200"
            }`}
          >
            {y}
          </button>
        ))}
      </div>
    </div>
  );
}

// ========== Salary Rankings ==========

function SalaryRankingsTab({ data }: { data: SalaryRankingsResponse }) {
  const years = data.years;
  const [selectedYear, setSelectedYear] = useState(
    years.length > 0 ? String(years[years.length - 1]) : "",
  );
  const ranking = data.rankings[selectedYear] ?? [];
  const maxSalary = ranking.length > 0 ? ranking[0].salary : 1;

  return (
    <div>
      <YearSelector years={years} selected={selectedYear} onChange={setSelectedYear} />
      <p className="mb-2 text-[11px] text-gray-400">
        {selectedYear} 賽季薪資排名前 20（Keepers + 選秀）
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="w-8 px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">#</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">球員</th>
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">約</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">薪資</th>
              <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 md:table-cell">分布</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">經理</th>
              <th className="hidden px-3 py-2 text-center text-[10px] font-medium uppercase text-gray-400 sm:table-cell">來源</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {ranking.map((p: SalaryRankingEntry) => (
              <tr key={`${p.player}-${p.rank}`} className="hover:bg-gray-50">
                <td className="px-2 py-1.5 text-center tabular-nums text-gray-300 sm:px-3 sm:py-2">
                  {p.rank}
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3 sm:py-2">
                  {p.player}
                </td>
                <td className="px-2 py-1.5 text-center sm:px-3 sm:py-2">
                  <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${contractBadgeColor(p.contract_type)}`}>
                    {p.contract_type}
                  </span>
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 text-right tabular-nums font-bold text-indigo-700 sm:px-3 sm:py-2">
                  ${p.salary}
                </td>
                <td className="hidden px-3 py-2 md:table-cell">
                  <div className="h-3 w-32 rounded-full bg-gray-100">
                    <div
                      className="h-3 rounded-full bg-indigo-500"
                      style={{ width: `${(p.salary / maxSalary) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 text-gray-500 sm:px-3 sm:py-2">{p.manager}</td>
                <td className="hidden px-3 py-2 text-center sm:table-cell">
                  <span className={`text-[10px] font-medium ${
                    p.source === "keeper" ? "text-blue-600" :
                    p.source === "draft" ? "text-green-600" :
                    "text-gray-400"
                  }`}>
                    {p.source === "keeper" ? "留用" :
                     p.source === "draft" ? "選秀" :
                     p.source === "trade_keeper" ? "交易" :
                     p.source}
                  </span>
                </td>
              </tr>
            ))}
            {ranking.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-gray-300 text-xs">
                  {selectedYear} 年無薪資資料
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ========== Contract Values ==========

function ContractValuesTab({ data }: { data: ContractValuesResponse }) {
  const contracts = data.contracts;
  const maxValue = contracts.length > 0 ? contracts[0].total_value : 1;

  return (
    <div>
      <p className="mb-2 text-[11px] text-gray-400">
        所有 N 約（延長合約）的總合約價值排名。年薪 x (B + N + O)
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="w-8 px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">#</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">球員</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">年薪</th>
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">年</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">總值</th>
              <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 md:table-cell">規模</th>
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">現況</th>
              <th className="hidden px-3 py-2 text-right text-[10px] font-medium uppercase text-gray-400 sm:table-cell">剩餘</th>
              <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 sm:table-cell">經理</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {contracts.map((c: ContractValue, idx: number) => {
              const pctComplete = ((c.total_years - c.years_remaining) / c.total_years) * 100;
              return (
                <tr key={c.player} className="hover:bg-gray-50 group">
                  <td className="px-2 py-1.5 text-center tabular-nums text-gray-300 sm:px-3 sm:py-2">
                    {idx + 1}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3 sm:py-2">
                    {c.player}
                    <div className="text-[9px] text-gray-400 sm:hidden">{c.manager}</div>
                    <div className="hidden text-[10px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity sm:block">
                      {c.manager_history.join(" -> ")}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right tabular-nums font-semibold sm:px-3 sm:py-2">
                    ${c.salary}
                  </td>
                  <td className="px-2 py-1.5 text-center tabular-nums text-gray-500 sm:px-3 sm:py-2">
                    {c.total_years}
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5 text-right tabular-nums font-bold text-indigo-700 sm:px-3 sm:py-2">
                    ${c.total_value}
                  </td>
                  <td className="hidden px-3 py-2 md:table-cell">
                    <div className="relative h-4 w-28 rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-indigo-500 opacity-30"
                        style={{ width: `${(c.total_value / maxValue) * 100}%` }}
                      />
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-indigo-600"
                        style={{ width: `${(c.total_value / maxValue) * pctComplete}%` }}
                      />
                    </div>
                    <div className="mt-0.5 text-[9px] text-gray-400">
                      已執行 {Math.round(pctComplete)}%
                    </div>
                  </td>
                  <td className="px-2 py-1.5 text-center sm:px-3 sm:py-2">
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${contractBadgeColor(c.current_contract)}`}>
                      {c.current_contract}
                    </span>
                  </td>
                  <td className="hidden px-3 py-2 text-right tabular-nums sm:table-cell">
                    <span className={`font-medium ${c.years_remaining <= 2 ? "text-red-600" : "text-gray-500"}`}>
                      {c.years_remaining}yr
                    </span>
                  </td>
                  <td className="hidden whitespace-nowrap px-3 py-2 text-gray-500 sm:table-cell">{c.manager}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {contracts.length > 0 && (
        <div className="mt-2 text-[10px] text-gray-400">
          共 {contracts.length} 份 N 約，承諾金額 ${contracts.reduce((s, c) => s + c.total_value, 0).toLocaleString()}
        </div>
      )}
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
        <div className="mb-2 inline-flex items-center gap-1.5 rounded-md border border-indigo-100 bg-indigo-50 px-2 py-1 text-[10px] text-indigo-700 sm:text-xs">
          <span className="font-semibold">最高:</span>
          <span>${summary.league_max.cost} {summary.league_max.player} ({summary.league_max.manager})</span>
        </div>
      )}

      <p className="mb-2 text-[11px] text-gray-400">
        每位 GM 選秀花費最高的前 10 筆。點擊展開明細。
      </p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th
                onClick={() => handleSort("manager")}
                className="cursor-pointer whitespace-nowrap px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 hover:text-gray-600 sm:px-3 sm:py-2"
              >
                經理{arrow("manager")}
              </th>
              <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 sm:table-cell">
                Top 10 花費
              </th>
              <th
                onClick={() => handleSort("top10_total")}
                className="cursor-pointer whitespace-nowrap px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 hover:text-gray-600 sm:px-3 sm:py-2"
              >
                小計{arrow("top10_total")}
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
                    <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3 sm:py-2">
                      <span className="mr-1 text-[10px] text-gray-300">
                        {isExpanded ? "\u25BC" : "\u25B6"}
                      </span>
                      {mgr}
                    </td>
                    <td className="hidden px-3 py-2 sm:table-cell">
                      <div className="flex items-center gap-0.5">
                        {yd.top_picks.map((p: DraftPick, i: number) => (
                          <div
                            key={i}
                            title={`${p.player} $${p.cost} (Rd ${p.round})`}
                            className={`h-5 rounded-sm ${costBarColor(p.cost)} transition-all hover:opacity-80`}
                            style={{ width: `${Math.max((p.cost / globalMax) * 100, 3)}%` }}
                          >
                            {p.cost >= 15 && (
                              <span className="flex h-full items-center justify-center text-[9px] font-bold text-white">
                                ${p.cost}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right tabular-nums font-semibold text-indigo-700 sm:px-3 sm:py-2">
                      ${yd.top10_total}
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr>
                      <td colSpan={3} className="bg-gray-50 px-3 py-2 sm:px-4 sm:py-3">
                        <div className="overflow-x-auto">
                          <table className="w-full text-[10px] sm:text-xs">
                            <thead>
                              <tr className="text-left text-gray-400">
                                <th className="w-6 pb-1 pr-1">#</th>
                                <th className="pb-1 pr-2">球員</th>
                                <th className="pb-1 pr-2">位置</th>
                                <th className="pb-1 pr-2 text-right">$</th>
                                <th className="hidden pb-1 pr-2 text-right sm:table-cell">Rd</th>
                              </tr>
                            </thead>
                            <tbody>
                              {yd.top_picks.map((p: DraftPick, i: number) => (
                                <tr key={i} className="border-t border-gray-100">
                                  <td className="py-0.5 pr-1 tabular-nums text-gray-300">{i + 1}</td>
                                  <td className="py-0.5 pr-2 font-medium text-gray-800">{p.player}</td>
                                  <td className="py-0.5 pr-2">
                                    <span
                                      className={`inline-block rounded px-1 py-0.5 text-[9px] font-medium ${POS_COLORS[_categorize(p.position)] ?? POS_COLORS.Unknown}`}
                                    >
                                      {p.position || "?"}
                                    </span>
                                  </td>
                                  <td className="py-0.5 pr-2 text-right tabular-nums font-semibold">${p.cost}</td>
                                  <td className="hidden py-0.5 pr-2 text-right tabular-nums text-gray-400 sm:table-cell">Rd {p.round}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div className="mt-1.5 text-[10px] text-gray-400">
                          全部 {yd.players_drafted} 筆，共 ${yd.total_spent}
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
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
          <MiniCard label="年度預算" value={`$${summary.faab_budget}`} />
          <MiniCard label="聯盟總花費" value={`$${summary.total_league_faab_spent}`} />
          <MiniCard label="平均花費" value={`$${summary.avg_team_faab_spent}`} />
          <MiniCard label="參與隊伍" value={`${summary.team_count}`} />
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">經理</th>
              <th onClick={() => handleSort("total_faab_spent")} className="cursor-pointer px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 hover:text-gray-600 sm:px-3 sm:py-2">
                花費{arrow("total_faab_spent")}
              </th>
              <th onClick={() => handleSort("remaining_pct")} className="cursor-pointer px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 hover:text-gray-600 sm:px-3 sm:py-2">
                餘%{arrow("remaining_pct")}
              </th>
              <th onClick={() => handleSort("num_pickups")} className="hidden cursor-pointer px-3 py-2 text-right text-[10px] font-medium uppercase text-gray-400 hover:text-gray-600 sm:table-cell">
                次數{arrow("num_pickups")}
              </th>
              <th className="hidden px-3 py-2 text-right text-[10px] font-medium uppercase text-gray-400 sm:table-cell">均價</th>
              <th onClick={() => handleSort("max_bid")} className="cursor-pointer px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 hover:text-gray-600 sm:px-3 sm:py-2">
                最高{arrow("max_bid")}
              </th>
              <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 md:table-cell">最高球員</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {sortedTeams.map(([mgr, teamData]) => {
              const yd = teamData.yearly[selectedYear];
              if (!yd) return null;
              return (
                <tr key={mgr} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3 sm:py-2">{mgr}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums sm:px-3 sm:py-2">${yd.total_faab_spent}</td>
                  <td className={`px-2 py-1.5 text-right tabular-nums sm:px-3 sm:py-2 ${yd.remaining_pct < 10 ? "font-medium text-red-600" : "text-gray-400"}`}>
                    {yd.remaining_pct}%
                  </td>
                  <td className="hidden px-3 py-2 text-right tabular-nums text-gray-400 sm:table-cell">{yd.num_pickups}</td>
                  <td className="hidden px-3 py-2 text-right tabular-nums text-gray-400 sm:table-cell">${yd.avg_bid}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums font-medium sm:px-3 sm:py-2">${yd.max_bid}</td>
                  <td className="hidden max-w-[120px] truncate px-3 py-2 text-gray-400 md:table-cell" title={yd.max_bid_player}>
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

      <div className="mb-3">
        <h3 className="mb-1.5 text-xs font-semibold text-gray-600">
          聯盟 $20+ 選秀位置分布
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {posCategories.map((pos) => (
            <span
              key={pos}
              className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium sm:text-xs ${POS_COLORS[pos] ?? POS_COLORS.Unknown}`}
            >
              {pos}: {data.league_position_breakdown[pos]}
            </span>
          ))}
          <span className="inline-flex items-center gap-0.5 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700 sm:text-xs">
            Total: {Object.values(data.league_position_breakdown).reduce((a, b) => a + b, 0)}
          </span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">經理</th>
              {posCategories.map((pos) => (
                <th key={pos} className="px-1.5 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">{pos}</th>
              ))}
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">$</th>
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
                const totalSpent = Object.values(teamData.yearly).reduce((s, yd) => s + yd.total_spent, 0);
                const isExpanded = expandedTeam === mgr;

                return (
                  <React.Fragment key={mgr}>
                    <tr className="cursor-pointer hover:bg-gray-50" onClick={() => setExpandedTeam(isExpanded ? null : mgr)}>
                      <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3 sm:py-2">
                        <span className="mr-0.5 text-[10px] text-gray-300">{isExpanded ? "\u25BC" : "\u25B6"}</span>
                        {mgr}
                      </td>
                      {posCategories.map((pos) => (
                        <td key={pos} className="px-1.5 py-1.5 text-center tabular-nums sm:px-3 sm:py-2">
                          {teamData.career_position_breakdown[pos] ? (
                            <span className={`inline-block min-w-[18px] rounded px-1 py-0.5 text-[9px] font-medium sm:text-xs ${POS_COLORS[pos] ?? POS_COLORS.Unknown}`}>
                              {teamData.career_position_breakdown[pos]}
                            </span>
                          ) : (
                            <span className="text-gray-200">-</span>
                          )}
                        </td>
                      ))}
                      <td className="px-2 py-1.5 text-center tabular-nums font-medium sm:px-3 sm:py-2">${totalSpent}</td>
                    </tr>

                    {isExpanded && (
                      <tr>
                        <td colSpan={posCategories.length + 2} className="bg-gray-50 px-3 py-2">
                          {years.map((y) => {
                            const yd = teamData.yearly[String(y)];
                            if (!yd) return null;
                            return (
                              <div key={y} className="mb-1.5">
                                <h4 className="mb-0.5 text-[10px] font-semibold text-gray-500">{y}</h4>
                                <div className="flex flex-wrap gap-1">
                                  {yd.picks
                                    .sort((a: { cost: number }, b: { cost: number }) => b.cost - a.cost)
                                    .map((p: { player: string; cost: number; position: string; pos_category: string }, i: number) => (
                                      <span
                                        key={i}
                                        className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] ${POS_COLORS[p.pos_category] ?? POS_COLORS.Unknown}`}
                                      >
                                        {p.player} ${p.cost}
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
        <div className="mb-3 grid grid-cols-3 gap-2">
          <MiniCard label="交易筆數" value={`${summary.total_trades}`} />
          <MiniCard label="參與隊伍" value={`${summary.team_count}`} />
          <MiniCard label="年份" value={selectedYear} />
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">經理</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">次數</th>
              <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 sm:table-cell">活躍度</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">送出</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">獲得</th>
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
                    <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3 sm:py-2">
                      <span className="mr-0.5 text-[10px] text-gray-300">{isExpanded ? "\u25BC" : "\u25B6"}</span>
                      {mgr}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums font-semibold text-indigo-700 sm:px-3 sm:py-2">
                      {yd.trade_count}
                    </td>
                    <td className="hidden px-3 py-2 sm:table-cell">
                      <div className="h-2.5 w-24 rounded-full bg-gray-200">
                        <div
                          className="h-2.5 rounded-full bg-indigo-500"
                          style={{ width: `${(yd.trade_count / maxTradeCount) * 100}%` }}
                        />
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-400 sm:px-3 sm:py-2">
                      {yd.players_sent.length}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-400 sm:px-3 sm:py-2">
                      {yd.players_received.length}
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr>
                      <td colSpan={5} className="bg-gray-50 px-3 py-2">
                        <div className="space-y-1.5">
                          {yd.trades.map((trade: TradeDetail, i: number) => {
                            const date = trade.timestamp
                              ? new Date(Number(trade.timestamp) * 1000).toLocaleDateString("zh-TW")
                              : "";
                            return (
                              <div key={i} className="rounded-md border border-gray-200 bg-white p-2 sm:p-3">
                                <div className="mb-1 flex items-center gap-1.5 text-[10px] text-gray-400 sm:text-xs">
                                  <span className="font-medium text-gray-600">#{i + 1}</span>
                                  <span>vs {trade.partner}</span>
                                  {date && <span>{date}</span>}
                                </div>
                                <div className="grid grid-cols-2 gap-2 text-[10px] sm:text-xs">
                                  <div>
                                    <span className="mb-0.5 block font-medium text-red-600">送出</span>
                                    <div className="flex flex-wrap gap-0.5">
                                      {trade.sent.map((name, j) => (
                                        <span key={j} className="rounded bg-red-50 px-1 py-0.5 text-red-700">
                                          {name}
                                        </span>
                                      ))}
                                      {trade.sent.length === 0 && <span className="text-gray-300">-</span>}
                                    </div>
                                  </div>
                                  <div>
                                    <span className="mb-0.5 block font-medium text-green-600">獲得</span>
                                    <div className="flex flex-wrap gap-0.5">
                                      {trade.received.map((name, j) => (
                                        <span key={j} className="rounded bg-green-50 px-1 py-0.5 text-green-700">
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
                <td colSpan={5} className="px-3 py-6 text-center text-xs text-gray-300">
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

// ========== Summary / Overview ==========

function SummaryTab({ data }: { data: LeagueSummaryResponse }) {
  const keeperYears = Object.keys(data.keeper_stats).sort();
  const draftYears = Object.keys(data.draft_highlights).sort();
  const tradeYears = Object.keys(data.trade_highlights).sort();
  const top5Contracts = data.contract_highlights.top5;

  return (
    <div className="space-y-5">
      {/* Top 5 Contracts */}
      <section>
        <h3 className="mb-2 text-sm font-semibold text-gray-900 sm:text-base">
          歷史合約 Top 5
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5 sm:gap-3">
          {top5Contracts.map((c: ContractValue, i: number) => (
            <div key={c.player} className={`rounded-lg border border-gray-200 bg-white p-2.5 text-center sm:p-3 ${i === 0 ? "col-span-2 sm:col-span-1" : ""}`}>
              <div className="text-base font-bold text-indigo-600 sm:text-lg">#{i + 1}</div>
              <div className="text-xs font-semibold text-gray-900 sm:text-sm">{c.player}</div>
              <div className="mt-0.5 text-[10px] text-gray-400">
                ${c.salary}/yr x {c.total_years}yr
              </div>
              <div className="mt-0.5 text-sm font-bold text-indigo-700 sm:text-lg">${c.total_value}</div>
              <div className="text-[10px] text-gray-400">{c.manager}</div>
            </div>
          ))}
        </div>
        <div className="mt-1.5 text-[10px] text-gray-400">
          共 {data.contract_highlights.total_n_contracts} 份 N 約，
          承諾金額 ${data.contract_highlights.total_committed_value.toLocaleString()}
        </div>
      </section>

      {/* Keeper Cost per Year */}
      <section>
        <h3 className="mb-2 text-sm font-semibold text-gray-900 sm:text-base">
          各年度留用花費
        </h3>
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">年</th>
                <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">最高</th>
                <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">$</th>
                <th className="hidden px-3 py-2 text-left text-[10px] font-medium uppercase text-gray-400 sm:table-cell">最低</th>
                <th className="hidden px-3 py-2 text-right text-[10px] font-medium uppercase text-gray-400 sm:table-cell">$</th>
                <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">平均</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {keeperYears.map((year) => {
                const ks = data.keeper_stats[year];
                return (
                  <tr key={year} className="hover:bg-gray-50">
                    <td className="px-2 py-1.5 font-semibold text-gray-900 sm:px-3 sm:py-2">{year}</td>
                    <td className="px-2 py-1.5 text-gray-600 sm:px-3 sm:py-2">{ks.highest_spender?.manager ?? "-"}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums font-medium text-indigo-700 sm:px-3 sm:py-2">
                      ${ks.highest_spender?.total_cost ?? 0}
                    </td>
                    <td className="hidden px-3 py-2 text-gray-600 sm:table-cell">{ks.lowest_spender?.manager ?? "-"}</td>
                    <td className="hidden px-3 py-2 text-right tabular-nums text-gray-400 sm:table-cell">
                      ${ks.lowest_spender?.total_cost ?? 0}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-gray-400 sm:px-3 sm:py-2">
                      ${ks.league_avg_cost}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Draft Highlights */}
      {draftYears.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-gray-900 sm:text-base">
            選秀概況
          </h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
            {draftYears.map((year) => {
              const dh = data.draft_highlights[year];
              return (
                <div key={year} className="rounded-lg border border-gray-200 bg-white p-2.5 sm:p-3">
                  <div className="mb-1 text-xs font-semibold text-gray-900">{year}</div>
                  <div className="space-y-0.5 text-[10px] sm:text-xs">
                    <Row label="選秀筆數" value={`${dh.total_picks}`} />
                    <Row label="總花費" value={`$${dh.total_spent}`} />
                    <Row label="平均" value={`$${dh.avg_pick_cost}`} />
                    <Row label="最高" value={`$${dh.max_pick}`} bold />
                    <Row label="大手筆" value={`${dh.biggest_spender.manager} ($${dh.biggest_spender.total})`} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Trade Activity */}
      {tradeYears.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-gray-900 sm:text-base">
            交易 & FAAB 活動
          </h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">年</th>
                  <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">交易</th>
                  <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">FAAB</th>
                  <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3 sm:py-2">全部</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {tradeYears.map((year) => {
                  const th = data.trade_highlights[year];
                  return (
                    <tr key={year} className="hover:bg-gray-50">
                      <td className="px-2 py-1.5 font-semibold text-gray-900 sm:px-3 sm:py-2">{year}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums font-medium text-indigo-700 sm:px-3 sm:py-2">{th.trade_count}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-gray-400 sm:px-3 sm:py-2">{th.faab_transactions}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums text-gray-400 sm:px-3 sm:py-2">{th.total_transactions}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

// ========== Shared ==========

function MiniCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-2 sm:p-3">
      <p className="text-[10px] font-medium text-gray-400 sm:text-xs">{label}</p>
      <p className="mt-0.5 text-sm font-bold text-gray-900 sm:text-base">{value}</p>
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-400">{label}</span>
      <span className={bold ? "font-bold text-indigo-700" : "font-medium"}>{value}</span>
    </div>
  );
}
