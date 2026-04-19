"use client";

import { Fragment, useEffect, useState, useCallback } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  getSubmissions,
  getYears,
  approveSubmission,
  getSubmissionDetail,
  unlockSubmission,
  clearKeeperSelections,
  getAllTeamAdjustments,
  updateTeamAdjustments,
  sendReminders,
  getReminderStatus,
  getPendingTeams,
  testLineConnection,
  testLinePush,
  verifyCommissionerPassword,
  getYahooTokenStatus,
  refreshYahooToken,
  testYahooConnection,
  disconnectYahooToken,
  syncRosters,
} from "@/lib/api";
import type { YahooTokenStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { SubmissionStatus, SubmissionDetail, TeamAdjustments } from "@/types";

type TeamStatus = "approved" | "submitted" | "rejected" | "pending";

function getTeamStatus(s: SubmissionStatus): TeamStatus {
  if (s.commissioner_approved) return "approved";
  if (s.is_submitted && s.commissioner_notes) return "rejected";
  if (s.is_submitted) return "submitted";
  return "pending";
}

const STATUS_CONFIG: Record<
  TeamStatus,
  { label: string; bg: string; border: string; badge: string; badgeText: string }
> = {
  approved: {
    label: "已審核 Approved",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-100",
    badgeText: "text-blue-700",
  },
  submitted: {
    label: "待審核 Pending Review",
    bg: "bg-green-50",
    border: "border-green-200",
    badge: "bg-green-100",
    badgeText: "text-green-700",
  },
  rejected: {
    label: "已退回 Rejected",
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100",
    badgeText: "text-red-700",
  },
  pending: {
    label: "未繳交 Not Submitted",
    bg: "bg-white",
    border: "border-gray-200",
    badge: "bg-gray-100",
    badgeText: "text-gray-500",
  },
};

// Sort order for submitted keeper selections
// Priority: O(1) → N(2) → B(3) → A(4) → R(5) → Buyout(6) → Release/FA(7)
function getSelectionSortOrder(sel: { current_contract?: string; action: string; next_contract?: string | null }): number {
  if (sel.action === "release" || sel.action === "release_normal") {
    return sel.current_contract?.includes("/N") ? 6 : 7;
  }
  const nc = sel.next_contract;
  if (!nc || nc === "FA") return 7;
  if (nc.includes("/O")) return 1;
  if (nc.includes("/N")) return 2;
  if (nc.includes("/B")) return 3;
  if (nc.includes("/A")) return 4;
  if (nc.includes("/R")) return 5;
  return 8;
}

const SELECTION_GROUP_CONFIG: Record<number, { label: string; style: string }> = {
  1: { label: "O 約 — 到期年 Final Year", style: "bg-gray-200 text-gray-700" },
  2: { label: "N 約 — 延長 Extension", style: "bg-blue-100 text-blue-800" },
  3: { label: "B 約 — 第二年 2nd Year", style: "bg-green-100 text-green-800" },
  4: { label: "A 約 — 第一年 1st Year", style: "bg-indigo-100 text-indigo-800" },
  5: { label: "R 約 — 農場新秀 Rookie", style: "bg-purple-100 text-purple-800" },
  6: { label: "買斷 Buyout", style: "bg-amber-100 text-amber-800" },
  7: { label: "不保留 Release / FA", style: "bg-red-100 text-red-800" },
  8: { label: "其他 Other", style: "bg-gray-100 text-gray-600" },
};

// Get action label and badge style based on contract type
// Key distinction: A/B release = free release, N release = paid buyout
function getSelectionDisplay(sel: { current_contract?: string; action: string; extension_years: number }): { label: string; className: string } {
  const isN = sel.current_contract?.includes("/N");

  if (sel.action === "keep") return { label: "留用 Keep", className: "bg-green-100 text-green-700" };

  if (sel.action === "release") {
    if (isN) return { label: "買斷 FAAB Buyout", className: "bg-amber-100 text-amber-700" };
    return { label: "不保留 Release", className: "bg-red-100 text-red-700" };
  }
  if (sel.action === "release_normal") {
    return { label: "買斷 Buyout (全薪資帽)", className: "bg-amber-100 text-amber-700" };
  }

  if (sel.action === "fa") return { label: "自由球員 Free Agent", className: "bg-gray-100 text-gray-500" };
  if (sel.action === "rookie") return { label: "新秀 Rookie", className: "bg-purple-100 text-purple-700" };
  if (sel.action === "activate") return { label: "啟用 Activate", className: "bg-indigo-100 text-indigo-700" };
  if (sel.action.startsWith("extend")) return { label: `延長 Extend ${sel.extension_years} 年`, className: "bg-blue-100 text-blue-700" };
  if (sel.action === "legal_issue") return { label: "法律問題 Legal Issue", className: "bg-gray-200 text-gray-600" };

  return { label: sel.action, className: "bg-gray-100 text-gray-700" };
}

export default function CommissionerDashboard() {
  const { user } = useAuth();

  // SWR cached years (consistent with other pages)
  const { data: yearsData = [] } = useSWR("years", getYears);
  const [selectedYear, setSelectedYear] = useState<number>(new Date().getFullYear());

  // Auto-select latest year if current year not available
  useEffect(() => {
    if (yearsData.length > 0 && !yearsData.includes(selectedYear)) {
      setSelectedYear(yearsData[yearsData.length - 1]);
    }
  }, [yearsData, selectedYear]);

  const years = yearsData;

  const [submissions, setSubmissions] = useState<SubmissionStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  // Detail expansion
  const [expandedTeam, setExpandedTeam] = useState<number | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Reject flow
  const [rejectingTeam, setRejectingTeam] = useState<number | null>(null);
  const [rejectNotes, setRejectNotes] = useState("");

  // Team adjustments
  const [adjustments, setAdjustments] = useState<Record<number, TeamAdjustments>>({});
  const [editingAdj, setEditingAdj] = useState<Record<number, { trade: string; faab: string }>>({});
  const [adjSaving, setAdjSaving] = useState<number | null>(null);
  const [showAdjustments, setShowAdjustments] = useState(false);

  // Reminder state
  const [showReminders, setShowReminders] = useState(false);
  const [pendingTeams, setPendingTeams] = useState<{
    pending_count: number;
    teams: Array<{ id: number; manager_name: string }>;
  } | null>(null);
  const [reminderHistory, setReminderHistory] = useState<Array<{
    id: number; team_id: number; manager_name: string; channel: string;
    sent_at: string; sent_by: string; status: string; error_message: string;
  }>>([]);
  const [reminderSending, setReminderSending] = useState(false);
  const [reminderResult, setReminderResult] = useState<{
    sent_to_group: boolean; pending_managers: string[];
    skipped_reason: string | null; error: string | null;
  } | null>(null);
  // LINE test state
  const [lineTestLoading, setLineTestLoading] = useState(false);
  const [lineTestResult, setLineTestResult] = useState<{
    success: boolean; message: string; group_id: string | null;
  } | null>(null);

  // LINE push test state (personal user / group / room)
  const [linePushTargetId, setLinePushTargetId] = useState("");
  const [linePushMessage, setLinePushMessage] = useState("");
  const [linePushLoading, setLinePushLoading] = useState(false);
  const [linePushResult, setLinePushResult] = useState<{
    success: boolean; message: string; target_id_preview: string;
  } | null>(null);

  // Yahoo API token state
  const [yahooToken, setYahooToken] = useState<YahooTokenStatus | null>(null);
  const [yahooTokenLoading, setYahooTokenLoading] = useState(false);
  const [yahooTokenMsg, setYahooTokenMsg] = useState("");

  const refreshSubmissions = useCallback(async () => {
    if (!selectedYear || !user?.is_commissioner) return;
    setLoading(true);
    setLoadError("");
    try {
      const data = await getSubmissions(selectedYear);
      setSubmissions(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[Commissioner] Failed to load submissions:", msg);
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  }, [selectedYear, user]);

  const refreshAdjustments = useCallback(async () => {
    if (!user?.is_commissioner) return;
    try {
      const data = await getAllTeamAdjustments();
      const map: Record<number, TeamAdjustments> = {};
      for (const adj of data) {
        map[adj.team_id] = adj;
      }
      setAdjustments(map);
    } catch {
      // ignore
    }
  }, [user]);

  const refreshReminders = useCallback(async () => {
    if (!user?.is_commissioner || !selectedYear) return;
    try {
      const [p, h] = await Promise.all([
        getPendingTeams(selectedYear),
        getReminderStatus(selectedYear),
      ]);
      setPendingTeams(p);
      setReminderHistory(h.history);
    } catch {
      // ignore
    }
  }, [selectedYear, user]);

  useEffect(() => {
    refreshSubmissions();
    refreshAdjustments();
    // Load Yahoo token status on mount
    if (user?.is_commissioner) {
      getYahooTokenStatus().then(setYahooToken).catch(() => {});
    }
  }, [refreshSubmissions, refreshAdjustments, user]);

  const handleAdjEdit = (teamId: number) => {
    const adj = adjustments[teamId];
    setEditingAdj((prev) => ({
      ...prev,
      [teamId]: {
        trade: String(adj?.trade_compensation ?? 0),
        faab: String(adj?.faab_adjustment ?? 0),
      },
    }));
  };

  const handleAdjCancel = (teamId: number) => {
    setEditingAdj((prev) => {
      const next = { ...prev };
      delete next[teamId];
      return next;
    });
  };

  const handleAdjSave = async (teamId: number) => {
    const edit = editingAdj[teamId];
    if (!edit) return;
    const trade = parseInt(edit.trade, 10) || 0;
    const faab = parseInt(edit.faab, 10) || 0;
    setAdjSaving(teamId);
    try {
      await updateTeamAdjustments(teamId, trade, faab);
      await refreshAdjustments();
      handleAdjCancel(teamId);
    } catch (e) {
      alert(e instanceof Error ? e.message : "儲存失敗");
    } finally {
      setAdjSaving(null);
    }
  };

  const handleToggleReminders = async () => {
    const next = !showReminders;
    setShowReminders(next);
    if (next) {
      setReminderResult(null);
      await refreshReminders();
    }
  };

  const handleSendReminders = async () => {
    if (!confirm("確定要發送 LINE 群組催繳通知？\nSend LINE group reminder to all pending teams?")) return;
    setReminderSending(true);
    setReminderResult(null);
    try {
      const result = await sendReminders(selectedYear);
      setReminderResult(result);
      await refreshReminders();
    } catch (e) {
      alert(e instanceof Error ? e.message : "發送失敗");
    } finally {
      setReminderSending(false);
    }
  };

  const handleLineTest = async () => {
    setLineTestLoading(true);
    setLineTestResult(null);
    try {
      const result = await testLineConnection();
      setLineTestResult(result);
    } catch (e) {
      setLineTestResult({
        success: false,
        message: e instanceof Error ? e.message : "Test failed",
        group_id: null,
      });
    } finally {
      setLineTestLoading(false);
    }
  };

  const handleLinePushTest = async () => {
    const target = linePushTargetId.trim();
    if (!target) {
      alert("請輸入 Target ID (U.../C.../R...)");
      return;
    }
    setLinePushLoading(true);
    setLinePushResult(null);
    try {
      const result = await testLinePush(target, linePushMessage.trim() || undefined);
      setLinePushResult(result);
    } catch (e) {
      setLinePushResult({
        success: false,
        message: e instanceof Error ? e.message : "Push failed",
        target_id_preview: target.slice(0, 6) + "...",
      });
    } finally {
      setLinePushLoading(false);
    }
  };

  const handleExpand = async (teamId: number) => {
    if (expandedTeam === teamId) {
      setExpandedTeam(null);
      setDetail(null);
      return;
    }
    setExpandedTeam(teamId);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getSubmissionDetail(selectedYear, teamId);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleApprove = async (teamId: number) => {
    try {
      await approveSubmission(selectedYear, teamId, true);
      await refreshSubmissions();
      setExpandedTeam(null);
      setDetail(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    }
  };

  const handleRejectStart = (teamId: number) => {
    setRejectingTeam(teamId);
    setRejectNotes("");
  };

  const handleRejectConfirm = async () => {
    if (!rejectingTeam || !rejectNotes.trim()) return;
    try {
      await approveSubmission(selectedYear, rejectingTeam, false, rejectNotes.trim());
      setRejectingTeam(null);
      setRejectNotes("");
      await refreshSubmissions();
      setExpandedTeam(null);
      setDetail(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    }
  };

  const handleUnlock = async (teamId: number, managerName: string) => {
    if (!confirm(`確定要解鎖 ${managerName} 的繳交？解鎖後該隊可重新編輯留用名單。`)) return;
    try {
      await unlockSubmission(selectedYear, teamId);
      await refreshSubmissions();
      setExpandedTeam(null);
      setDetail(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    }
  };

  const handleClearSelections = async (teamId: number, managerName: string) => {
    if (!confirm(
      `確定要清除 ${managerName} 的所有留用選擇？\n此操作會同時移除繳交記錄，該隊需要重新填寫。\nThis will remove all keeper selections and submission records.`
    )) return;
    try {
      await clearKeeperSelections(selectedYear, teamId);
      await refreshSubmissions();
      setExpandedTeam(null);
      setDetail(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    }
  };

  if (!user?.is_commissioner) {
    return <CommissionerLogin />;
  }

  const statusCounts = submissions.reduce(
    (acc, s) => {
      const status = getTeamStatus(s);
      acc[status]++;
      return acc;
    },
    { approved: 0, submitted: 0, rejected: 0, pending: 0 } as Record<TeamStatus, number>,
  );

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold sm:text-2xl">Commissioner 管理面板</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 sm:gap-3">
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="rounded border px-2 py-1.5 text-sm sm:px-3"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <Link
            href="/commissioner/users"
            className="inline-flex min-h-[44px] items-center rounded bg-gray-600 px-2.5 py-1.5 text-xs text-white hover:bg-gray-500 sm:min-h-0 sm:px-3 sm:text-sm"
          >
            用戶管理
          </Link>
          <Link
            href="/commissioner/buyouts"
            className="inline-flex min-h-[44px] items-center rounded bg-amber-600 px-2.5 py-1.5 text-xs text-white hover:bg-amber-500 sm:min-h-0 sm:px-3 sm:text-sm"
          >
            Buyout Management
          </Link>
          <Link
            href="/commissioner/import"
            className="inline-flex min-h-[44px] items-center rounded bg-indigo-600 px-2.5 py-1.5 text-xs text-white hover:bg-indigo-500 sm:min-h-0 sm:px-3 sm:text-sm"
          >
            匯入 Excel
          </Link>
          <button
            onClick={async () => {
              // Always sync current MLB season (current year), not the selected year
              // e.g. selectedYear=2027 page shows "2026 season roster",
              // so we sync 2026 rosters and rebuild 2027 snapshot
              const syncYear = new Date().getFullYear();
              if (!confirm(
                `從 Yahoo 同步 ${syncYear} 賽季最新名冊並重建 ${syncYear + 1} snapshot？\n` +
                `Sync ${syncYear} rosters from Yahoo and rebuild ${syncYear + 1} snapshot?`
              )) return;
              try {
                const r = await syncRosters(syncYear);
                alert(`同步完成: ${r.teams} 隊, ${r.total_players} 球員`);
              } catch (e) {
                alert(e instanceof Error ? e.message : "同步失敗");
              }
            }}
            className="inline-flex min-h-[44px] items-center rounded bg-teal-600 px-2.5 py-1.5 text-xs text-white hover:bg-teal-500 sm:min-h-0 sm:px-3 sm:text-sm"
          >
            同步名冊
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5 sm:gap-4">
        <div className="rounded-lg border bg-white px-3 py-2 sm:px-4 sm:py-3">
          <p className="text-[10px] text-gray-500 sm:text-xs">總隊伍</p>
          <p className="text-xl font-bold sm:text-2xl">{submissions.length}</p>
        </div>
        <div className="rounded-lg border bg-green-50 px-3 py-2 sm:px-4 sm:py-3">
          <p className="text-[10px] text-gray-500 sm:text-xs">待審核</p>
          <p className="text-xl font-bold text-green-600 sm:text-2xl">
            {statusCounts.submitted}
          </p>
        </div>
        <div className="rounded-lg border bg-blue-50 px-3 py-2 sm:px-4 sm:py-3">
          <p className="text-[10px] text-gray-500 sm:text-xs">已審核</p>
          <p className="text-xl font-bold text-blue-600 sm:text-2xl">
            {statusCounts.approved}
          </p>
        </div>
        <div className="rounded-lg border bg-red-50 px-3 py-2 sm:px-4 sm:py-3">
          <p className="text-[10px] text-gray-500 sm:text-xs">已退回</p>
          <p className="text-xl font-bold text-red-600 sm:text-2xl">
            {statusCounts.rejected}
          </p>
        </div>
        <div className="rounded-lg border bg-yellow-50 px-3 py-2 sm:px-4 sm:py-3">
          <p className="text-[10px] text-gray-500 sm:text-xs">未繳交</p>
          <p className="text-xl font-bold text-yellow-600 sm:text-2xl">
            {statusCounts.pending}
          </p>
        </div>
      </div>

      {/* Yahoo API Connection Status */}
      {yahooToken !== null && (
        <div className={`mb-6 rounded-lg border p-4 ${
          yahooToken.connected
            ? yahooToken.is_expired
              ? "border-amber-300 bg-amber-50"
              : "border-green-300 bg-green-50"
            : "border-gray-300 bg-gray-50"
        }`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2.5 w-2.5 rounded-full ${
                yahooToken.connected
                  ? yahooToken.is_expired ? "bg-amber-500" : "bg-green-500"
                  : "bg-gray-400"
              }`} />
              <h3 className="text-sm font-semibold text-gray-700">
                Yahoo API 連結狀態
              </h3>
              <span className={`text-xs ${
                yahooToken.connected
                  ? yahooToken.is_expired ? "text-amber-600" : "text-green-600"
                  : "text-gray-500"
              }`}>
                {yahooToken.message}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {yahooToken.connected && (
                <>
                  <button
                    onClick={async () => {
                      setYahooTokenLoading(true);
                      setYahooTokenMsg("");
                      try {
                        const result = await refreshYahooToken();
                        setYahooToken(result);
                        setYahooTokenMsg("Token 已刷新");
                      } catch (e) {
                        setYahooTokenMsg(e instanceof Error ? e.message : "刷新失敗");
                      } finally {
                        setYahooTokenLoading(false);
                      }
                    }}
                    disabled={yahooTokenLoading}
                    className="rounded bg-blue-500 px-2 py-1 text-xs text-white hover:bg-blue-400 disabled:opacity-50"
                  >
                    {yahooTokenLoading ? "..." : "Refresh Token"}
                  </button>
                  <button
                    onClick={async () => {
                      setYahooTokenLoading(true);
                      setYahooTokenMsg("");
                      try {
                        const result = await testYahooConnection();
                        setYahooTokenMsg(result.message);
                      } catch (e) {
                        setYahooTokenMsg(e instanceof Error ? e.message : "測試失敗");
                      } finally {
                        setYahooTokenLoading(false);
                      }
                    }}
                    disabled={yahooTokenLoading}
                    className="rounded bg-gray-500 px-2 py-1 text-xs text-white hover:bg-gray-400 disabled:opacity-50"
                  >
                    Test Connection
                  </button>
                  <button
                    onClick={async () => {
                      if (!confirm("確定要斷開 Yahoo API 連結？\nDisconnect Yahoo API?")) return;
                      try {
                        await disconnectYahooToken();
                        setYahooToken({
                          connected: false, user_id: null, yahoo_guid: "",
                          expires_at: null, is_expired: false, updated_at: null,
                          message: "Yahoo API 尚未連結 Not connected",
                        });
                        setYahooTokenMsg("已斷開連結");
                      } catch (e) {
                        setYahooTokenMsg(e instanceof Error ? e.message : "操作失敗");
                      }
                    }}
                    className="rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                  >
                    Disconnect
                  </button>
                </>
              )}
              {!yahooToken.connected && (
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002"}/api/auth/yahoo/login`}
                  className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-500"
                >
                  重新登入 Yahoo Re-authorize
                </a>
              )}
            </div>
          </div>
          {yahooToken.connected && yahooToken.expires_at && (
            <p className="mt-1 text-[10px] text-gray-500">
              Token 到期: {new Date(yahooToken.expires_at).toLocaleString()} | 最後更新: {yahooToken.updated_at ? new Date(yahooToken.updated_at).toLocaleString() : "-"}
            </p>
          )}
          {yahooTokenMsg && (
            <p className="mt-1 text-xs text-blue-600">{yahooTokenMsg}</p>
          )}
        </div>
      )}

      {/* Trade & FAAB Adjustments */}
      <div className="mb-6">
        <button
          onClick={() => setShowAdjustments(!showAdjustments)}
          className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-700 hover:text-gray-900"
        >
          <span>{showAdjustments ? "\u25BC" : "\u25B6"}</span>
          交易薪資 / FAAB 調整 Trade & FAAB Adjustments
        </button>
        {showAdjustments && (
          <div className="overflow-x-auto rounded-lg border bg-white">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
                    隊伍 Team
                  </th>
                  <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                    交易補償 Trade Comp.
                  </th>
                  <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                    FAAB 調整 Adjustment
                  </th>
                  <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                    操作 Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {submissions.map((s) => {
                  const adj = adjustments[s.team_id];
                  const isEditing = !!editingAdj[s.team_id];
                  const isSaving = adjSaving === s.team_id;
                  const tradeVal = adj?.trade_compensation ?? 0;
                  const faabVal = adj?.faab_adjustment ?? 0;

                  return (
                    <tr key={s.team_id} className="border-b last:border-0">
                      <td className="px-3 py-2 font-medium">{s.manager_name}</td>
                      <td className="px-3 py-2 text-center">
                        {isEditing ? (
                          <input
                            type="number"
                            value={editingAdj[s.team_id].trade}
                            onChange={(e) =>
                              setEditingAdj((prev) => ({
                                ...prev,
                                [s.team_id]: { ...prev[s.team_id], trade: e.target.value },
                              }))
                            }
                            className="w-20 rounded border px-2 py-1 text-center text-sm"
                          />
                        ) : (
                          <span
                            className={
                              tradeVal > 0
                                ? "font-semibold text-purple-600"
                                : tradeVal < 0
                                  ? "font-semibold text-orange-600"
                                  : "text-gray-400"
                            }
                          >
                            {tradeVal > 0 ? `+$${tradeVal}` : tradeVal < 0 ? `-$${Math.abs(tradeVal)}` : "$0"}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {isEditing ? (
                          <input
                            type="number"
                            value={editingAdj[s.team_id].faab}
                            onChange={(e) =>
                              setEditingAdj((prev) => ({
                                ...prev,
                                [s.team_id]: { ...prev[s.team_id], faab: e.target.value },
                              }))
                            }
                            className="w-20 rounded border px-2 py-1 text-center text-sm"
                          />
                        ) : (
                          <span
                            className={
                              faabVal > 0
                                ? "font-semibold text-purple-600"
                                : faabVal < 0
                                  ? "font-semibold text-orange-600"
                                  : "text-gray-400"
                            }
                          >
                            {faabVal > 0 ? `+$${faabVal}` : faabVal < 0 ? `-$${Math.abs(faabVal)}` : "$0"}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {isEditing ? (
                          <div className="flex items-center justify-center gap-1">
                            <button
                              onClick={() => handleAdjSave(s.team_id)}
                              disabled={isSaving}
                              className="rounded bg-green-600 px-2 py-0.5 text-xs text-white hover:bg-green-500 disabled:opacity-50"
                            >
                              {isSaving ? "..." : "儲存"}
                            </button>
                            <button
                              onClick={() => handleAdjCancel(s.team_id)}
                              className="rounded border px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
                            >
                              取消
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleAdjEdit(s.team_id)}
                            className="rounded border px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-50"
                          >
                            編輯
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Keeper Reminders (LINE) */}
      <div className="mb-6">
        <button
          onClick={handleToggleReminders}
          className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-700 hover:text-gray-900"
        >
          <span>{showReminders ? "\u25BC" : "\u25B6"}</span>
          催繳提醒 Keeper Reminders (LINE)
        </button>
        {showReminders && (
          <div className="rounded-lg border bg-white p-4">
            {/* Pending summary + action buttons */}
            <div className="mb-4 flex flex-wrap items-center gap-4">
              <div className="rounded bg-yellow-50 px-3 py-2">
                <p className="text-xs text-gray-500">未繳交 Pending</p>
                <p className="text-lg font-bold text-yellow-600">
                  {pendingTeams?.pending_count ?? "-"} 隊
                </p>
              </div>
              <button
                onClick={handleSendReminders}
                disabled={reminderSending || !pendingTeams || pendingTeams.pending_count === 0}
                className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
              >
                {reminderSending ? "發送中..." : "發送 LINE 催繳 Send LINE Reminder"}
              </button>
              <button
                onClick={handleLineTest}
                disabled={lineTestLoading}
                className="rounded bg-gray-200 px-3 py-2 text-sm text-gray-700 hover:bg-gray-300 disabled:opacity-50"
              >
                {lineTestLoading ? "測試中..." : "測試 LINE 連線 Test LINE"}
              </button>
            </div>

            {/* LINE test result */}
            {lineTestResult && (
              <div className={`mb-4 rounded border p-3 text-sm ${
                lineTestResult.success ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"
              }`}>
                <p className={lineTestResult.success ? "text-green-700" : "text-red-700"}>
                  {lineTestResult.success ? "LINE 連線正常" : "LINE 連線失敗"}:{" "}
                  {lineTestResult.message}
                </p>
                {lineTestResult.group_id && (
                  <p className="mt-1 text-xs text-gray-500">Group ID: {lineTestResult.group_id}</p>
                )}
              </div>
            )}

            {/* LINE push test (personal / arbitrary target) */}
            <div className="mb-4 rounded border border-blue-200 bg-blue-50 p-3">
              <p className="mb-2 text-xs font-semibold text-blue-800">
                LINE 個人推送測試 Personal Push Test
              </p>
              <p className="mb-2 text-xs text-gray-600">
                指定 LINE Target ID（U... 使用者 / C... 群組 / R... 聊天室）。Bot 需為對方好友或群組成員才能推送成功。
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  type="text"
                  value={linePushTargetId}
                  onChange={(e) => setLinePushTargetId(e.target.value)}
                  placeholder="Target ID (U... / C... / R...)"
                  className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm font-mono focus:border-indigo-500 focus:ring-indigo-500"
                />
                <input
                  type="text"
                  value={linePushMessage}
                  onChange={(e) => setLinePushMessage(e.target.value)}
                  placeholder="自訂訊息 (可留空，使用預設測試文字)"
                  className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                />
                <button
                  onClick={handleLinePushTest}
                  disabled={linePushLoading}
                  className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  {linePushLoading ? "推送中..." : "推送 Push"}
                </button>
              </div>
              {linePushResult && (
                <div className={`mt-2 rounded border p-2 text-xs ${
                  linePushResult.success ? "border-green-200 bg-green-100" : "border-red-200 bg-red-100"
                }`}>
                  <p className={linePushResult.success ? "text-green-700" : "text-red-700"}>
                    {linePushResult.success ? "推送成功" : "推送失敗"}：{linePushResult.message}
                  </p>
                  <p className="mt-1 text-gray-500">Target: {linePushResult.target_id_preview}</p>
                </div>
              )}
            </div>

            {/* Send result */}
            {reminderResult && (
              <div className="mb-4 rounded border bg-gray-50 p-3 text-sm">
                <p className="mb-1 font-semibold">發送結果 Result:</p>
                {reminderResult.sent_to_group && (
                  <p className="text-green-600">
                    已發送至 LINE 群組 Sent to LINE group ({reminderResult.pending_managers.length} 隊未繳交)
                  </p>
                )}
                {reminderResult.skipped_reason === "cooldown" && (
                  <p className="text-yellow-600">
                    跳過 Skipped (冷卻時間內，請稍後再試 Cooldown active)
                  </p>
                )}
                {reminderResult.skipped_reason === "all_submitted" && (
                  <p className="text-green-600">
                    所有隊伍已繳交 All teams submitted
                  </p>
                )}
                {reminderResult.error && (
                  <p className="text-red-600">
                    發送失敗 Failed: {reminderResult.error}
                  </p>
                )}
              </div>
            )}

            {/* Pending teams list */}
            {pendingTeams && pendingTeams.teams.length > 0 && (
              <div className="mb-4">
                <p className="mb-2 text-xs font-medium text-gray-500">
                  未繳交隊伍 Pending Teams
                </p>
                <div className="flex flex-wrap gap-2">
                  {pendingTeams.teams.map((t) => (
                    <span
                      key={t.id}
                      className="rounded bg-yellow-100 px-2 py-1 text-xs text-yellow-700"
                    >
                      {t.manager_name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Reminder history */}
            {reminderHistory.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium text-gray-500">
                  最近催繳紀錄 Recent History
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="border-b bg-gray-50">
                      <tr>
                        <th className="px-2 py-1.5 text-left text-gray-500">管道 Channel</th>
                        <th className="px-2 py-1.5 text-left text-gray-500">時間 Time</th>
                        <th className="px-2 py-1.5 text-left text-gray-500">發送者 By</th>
                        <th className="px-2 py-1.5 text-left text-gray-500">狀態 Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reminderHistory.slice(0, 20).map((h) => (
                        <tr key={h.id} className="border-b last:border-0">
                          <td className="px-2 py-1.5">
                            <span className={`rounded px-1 py-0.5 ${
                              h.channel === "line"
                                ? "bg-green-100 text-green-700"
                                : "bg-blue-100 text-blue-700"
                            }`}>
                              {h.channel === "line" ? "LINE" : "Email"}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 text-gray-500">
                            {new Date(h.sent_at).toLocaleString("zh-TW")}
                          </td>
                          <td className="px-2 py-1.5">
                            <span className={`rounded px-1 py-0.5 ${
                              h.sent_by === "scheduler"
                                ? "bg-blue-100 text-blue-700"
                                : "bg-purple-100 text-purple-700"
                            }`}>
                              {h.sent_by === "scheduler" ? "排程 Auto" : "手動 Manual"}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            <span className={`rounded px-1 py-0.5 ${
                              h.status === "sent"
                                ? "bg-green-100 text-green-700"
                                : h.status === "failed"
                                  ? "bg-red-100 text-red-700"
                                  : "bg-gray-100 text-gray-500"
                            }`}>
                              {h.status === "sent" ? "已送出" : h.status === "failed" ? "失敗" : "跳過"}
                            </span>
                            {h.error_message && (
                              <span className="ml-1 text-red-500" title={h.error_message}>
                                ({h.error_message})
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {reminderHistory.length === 0 && pendingTeams?.pending_count === 0 && (
              <p className="text-sm text-green-600">
                所有隊伍已繳交留用名單! All teams have submitted.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Reject Modal */}
      {rejectingTeam !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-4 shadow-lg sm:p-6">
            <h3 className="mb-3 text-lg font-semibold">退回留用名單 Reject Keeper List</h3>
            <p className="mb-3 text-sm text-gray-600">
              退回原因（必填）：
            </p>
            <textarea
              className="mb-4 w-full rounded border p-2 text-sm"
              rows={4}
              value={rejectNotes}
              onChange={(e) => setRejectNotes(e.target.value)}
              placeholder="請說明退回原因，例如：某球員合約選擇不正確..."
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setRejectingTeam(null)}
                className="rounded border px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleRejectConfirm}
                disabled={!rejectNotes.trim()}
                className="rounded bg-red-600 px-4 py-1.5 text-sm text-white hover:bg-red-500 disabled:opacity-50"
              >
                確認退回
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {loadError && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          <p className="font-semibold">載入失敗 Load Error</p>
          <p className="mt-1">{loadError}</p>
        </div>
      )}

      {/* Team Cards */}
      {loading ? (
        <p className="text-gray-500">載入中...</p>
      ) : (
        <div className="space-y-3">
          {submissions.map((s) => {
            const status = getTeamStatus(s);
            const cfg = STATUS_CONFIG[status];
            const isExpanded = expandedTeam === s.team_id;

            return (
              <div key={s.team_id}>
                {/* Card */}
                <div
                  className={`rounded-lg border p-3 sm:p-4 ${cfg.border} ${cfg.bg}`}
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{s.manager_name}</h3>
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs ${cfg.badge} ${cfg.badgeText}`}
                        >
                          {cfg.label}
                        </span>
                      </div>
                      {s.team_name && (
                        <p className="text-xs text-gray-500">{s.team_name}</p>
                      )}
                      {s.submitted_at && (
                        <p className="text-xs text-gray-400">
                          繳交：{new Date(s.submitted_at).toLocaleString("zh-TW")}
                        </p>
                      )}
                      {status === "rejected" && s.commissioner_notes && (
                        <p className="mt-1 text-xs text-red-600">
                          退回原因：{s.commissioner_notes}
                        </p>
                      )}
                    </div>

                    {/* Action buttons */}
                    <div className="flex flex-wrap items-center gap-2">
                      {s.is_submitted && (
                        <button
                          onClick={() => handleExpand(s.team_id)}
                          className="min-h-[44px] rounded border bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-50 sm:min-h-0"
                        >
                          {isExpanded ? "收合" : "詳情"}
                        </button>
                      )}

                      {status === "submitted" && (
                        <>
                          <button
                            onClick={() => handleApprove(s.team_id)}
                            className="min-h-[44px] rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-500 sm:min-h-0"
                          >
                            通過
                          </button>
                          <button
                            onClick={() => handleRejectStart(s.team_id)}
                            className="min-h-[44px] rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-500 sm:min-h-0"
                          >
                            退回
                          </button>
                        </>
                      )}

                      {status === "approved" && (
                        <button
                          onClick={() => handleUnlock(s.team_id, s.manager_name)}
                          className="min-h-[44px] rounded border border-yellow-400 bg-yellow-50 px-3 py-1 text-xs text-yellow-700 hover:bg-yellow-100 sm:min-h-0"
                        >
                          解鎖
                        </button>
                      )}

                      {status === "pending" && (
                        <Link
                          href={`/${selectedYear}/${s.team_id}`}
                          className="inline-flex min-h-[44px] items-center rounded border bg-white px-3 py-1 text-xs text-indigo-600 hover:bg-indigo-50 sm:min-h-0"
                        >
                          查看名單
                        </Link>
                      )}

                      <button
                        onClick={() => handleClearSelections(s.team_id, s.manager_name)}
                        className="min-h-[44px] rounded border border-red-200 px-3 py-1 text-xs text-red-500 hover:bg-red-50 sm:min-h-0"
                        title="清除該隊所有留用選擇及繳交記錄"
                      >
                        清除選擇
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div className="rounded-b-lg border border-t-0 border-gray-200 bg-white p-4">
                    {detailLoading ? (
                      <p className="text-sm text-gray-500">載入詳情...</p>
                    ) : detail ? (
                      <div className="space-y-4">
                        {/* Selections table */}
                        <div>
                          <h4 className="mb-2 text-sm font-semibold">留用選擇 Keeper Selections</h4>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                                  <th className="px-3 py-2">球員 Player</th>
                                  <th className="px-3 py-2">現約 Current</th>
                                  <th className="px-3 py-2">操作 Action</th>
                                  <th className="px-3 py-2">新約 Next</th>
                                </tr>
                              </thead>
                              <tbody>
                                {[...detail.selections]
                                  .sort((a, b) => {
                                    const orderA = getSelectionSortOrder(a);
                                    const orderB = getSelectionSortOrder(b);
                                    return orderA - orderB;
                                  })
                                  .map((sel, idx, sorted) => {
                                    const order = getSelectionSortOrder(sel);
                                    const prevOrder = idx > 0 ? getSelectionSortOrder(sorted[idx - 1]) : -1;
                                    const showHeader = order !== prevOrder;
                                    const groupCfg = SELECTION_GROUP_CONFIG[order] || SELECTION_GROUP_CONFIG[8];
                                    return (
                                      <Fragment key={sel.player_name}>
                                        {showHeader && (
                                          <tr>
                                            <td
                                              colSpan={4}
                                              className={`px-3 py-1 text-xs font-bold ${groupCfg.style}`}
                                            >
                                              {groupCfg.label}
                                            </td>
                                          </tr>
                                        )}
                                        <tr className="border-b last:border-0">
                                          <td className="px-3 py-1.5">{sel.player_name}</td>
                                          <td className="px-3 py-1.5 font-mono text-xs">
                                            {sel.current_contract}
                                          </td>
                                          <td className="px-3 py-1.5">
                                            {(() => {
                                              const display = getSelectionDisplay(sel);
                                              return (
                                                <span className={`rounded px-1.5 py-0.5 text-xs ${display.className}`}>
                                                  {display.label}
                                                </span>
                                              );
                                            })()}
                                          </td>
                                          <td className="px-3 py-1.5 font-mono text-xs">
                                            {sel.next_contract || "-"}
                                          </td>
                                        </tr>
                                      </Fragment>
                                    );
                                  })}
                              </tbody>
                            </table>
                          </div>
                        </div>

                        {/* Financial summary */}
                        {detail.validation_result?.financial_summary && (
                          <div>
                            <h4 className="mb-2 text-sm font-semibold">財務摘要 Financial Summary</h4>
                            <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
                              {(() => {
                                const f = detail.validation_result.financial_summary;
                                const hasBuyout = f.buyout_salary_cost > 0 || f.buyout_faab_cost > 0;
                                return (
                                  <>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">薪資上限 Salary Cap</p>
                                      <p className="font-semibold">${f.salary_cap}</p>
                                    </div>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">留用成本 Keeper Cost</p>
                                      <p className="font-semibold">${f.keeper_cost}</p>
                                    </div>
                                    {hasBuyout && (
                                      <div className="rounded bg-amber-50 p-2">
                                        <p className="text-xs text-gray-500">買斷成本 Buyout</p>
                                        <p className="font-semibold text-amber-700">
                                          ${f.buyout_salary_cost} Cap
                                          {f.buyout_faab_cost > 0 && (
                                            <span className="text-xs font-normal text-amber-600"> + ${f.buyout_faab_cost} FAAB</span>
                                          )}
                                        </p>
                                      </div>
                                    )}
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">可用薪資 Cap Space</p>
                                      <p className={`font-semibold ${f.available_salary < 0 ? "text-red-600" : ""}`}>
                                        ${f.available_salary}
                                      </p>
                                    </div>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">
                                        留用人數 Keepers (Active/Farm)
                                      </p>
                                      <p className="font-semibold">
                                        {f.active_keeper_count} / {f.farm_rookie_count}
                                      </p>
                                    </div>
                                  </>
                                );
                              })()}
                            </div>
                          </div>
                        )}

                        {/* Validation errors/warnings */}
                        {detail.validation_result && (
                          <div>
                            {detail.validation_result.errors.length > 0 && (
                              <div className="mb-2">
                                <h4 className="mb-1 text-sm font-semibold text-red-600">
                                  驗證錯誤 Validation Errors
                                </h4>
                                <ul className="list-inside list-disc text-sm text-red-600">
                                  {detail.validation_result.errors.map((e, i) => (
                                    <li key={i}>{e}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {detail.validation_result.warnings.length > 0 && (
                              <div>
                                <h4 className="mb-1 text-sm font-semibold text-yellow-600">
                                  警告 Warnings
                                </h4>
                                <ul className="list-inside list-disc text-sm text-yellow-600">
                                  {detail.validation_result.warnings.map((w, i) => (
                                    <li key={i}>{w}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {detail.validation_result.errors.length === 0 &&
                              detail.validation_result.warnings.length === 0 && (
                                <p className="text-sm text-green-600">
                                  驗證通過 Validation Passed，無錯誤或警告。
                                </p>
                              )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-red-500">無法載入詳情</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ========== Commissioner Login (Password Prompt) ========== */

function CommissionerLogin() {
  const { user, refresh } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [verifying, setVerifying] = useState(false);

  const handleVerify = async () => {
    if (!password.trim()) return;
    setVerifying(true);
    setError("");
    try {
      await verifyCommissionerPassword(password.trim());
      // Backend set new HttpOnly cookie; refresh auth context
      await refresh();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "驗證失敗 Verification failed",
      );
    } finally {
      setVerifying(false);
    }
  };

  if (!user) {
    return (
      <div className="py-10 text-center text-gray-500">
        請先登入 Yahoo 帳號。
        <br />
        <a
          href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002"}/api/auth/yahoo/login`}
          className="mt-4 inline-block rounded bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500"
        >
          Login with Yahoo
        </a>
      </div>
    );
  }

  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="w-full max-w-sm rounded-lg border bg-white p-6 shadow-sm">
        <h2 className="mb-1 text-lg font-bold">Commissioner 管理面板</h2>
        <p className="mb-4 text-sm text-gray-500">
          請輸入管理密碼以進入 Commissioner 面板。
        </p>
        <div className="space-y-3">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleVerify()}
            placeholder="管理密碼 Password"
            className="w-full rounded border px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            autoFocus
          />
          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
          <button
            onClick={handleVerify}
            disabled={verifying || !password.trim()}
            className="w-full rounded bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {verifying ? "驗證中..." : "進入管理面板 Enter"}
          </button>
        </div>
      </div>
    </div>
  );
}
