"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  getSubmissions,
  getYears,
  approveSubmission,
  getSubmissionDetail,
  unlockSubmission,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { SubmissionStatus, SubmissionDetail } from "@/types";

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
    label: "已審核",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-100",
    badgeText: "text-blue-700",
  },
  submitted: {
    label: "待審核",
    bg: "bg-green-50",
    border: "border-green-200",
    badge: "bg-green-100",
    badgeText: "text-green-700",
  },
  rejected: {
    label: "已退回",
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100",
    badgeText: "text-red-700",
  },
  pending: {
    label: "未繳交",
    bg: "bg-white",
    border: "border-gray-200",
    badge: "bg-gray-100",
    badgeText: "text-gray-500",
  },
};

export default function CommissionerDashboard() {
  const { user } = useAuth();
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number>(
    new Date().getFullYear(),
  );
  const [submissions, setSubmissions] = useState<SubmissionStatus[]>([]);
  const [loading, setLoading] = useState(false);

  // Detail expansion
  const [expandedTeam, setExpandedTeam] = useState<number | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Reject flow
  const [rejectingTeam, setRejectingTeam] = useState<number | null>(null);
  const [rejectNotes, setRejectNotes] = useState("");

  useEffect(() => {
    getYears().then((y) => {
      setYears(y);
      if (y.length > 0 && !y.includes(selectedYear)) {
        setSelectedYear(y[y.length - 1]);
      }
    });
  }, []);

  const refreshSubmissions = useCallback(async () => {
    if (!selectedYear || !user?.is_commissioner) return;
    setLoading(true);
    try {
      const data = await getSubmissions(selectedYear);
      setSubmissions(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [selectedYear, user]);

  useEffect(() => {
    refreshSubmissions();
  }, [refreshSubmissions]);

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

  if (!user?.is_commissioner) {
    return (
      <div className="py-10 text-center text-red-600">
        需要 Commissioner 權限才能存取此頁面。
      </div>
    );
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
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Commissioner 管理面板</h1>
        <div className="flex items-center gap-3">
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="rounded border px-3 py-1.5"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <Link
            href="/commissioner/users"
            className="rounded bg-gray-600 px-3 py-1.5 text-sm text-white hover:bg-gray-500"
          >
            用戶管理
          </Link>
          <Link
            href="/commissioner/import"
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500"
          >
            匯入 Excel
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 flex flex-wrap gap-4">
        <div className="rounded-lg border bg-white px-4 py-3">
          <p className="text-xs text-gray-500">總隊伍</p>
          <p className="text-2xl font-bold">{submissions.length}</p>
        </div>
        <div className="rounded-lg border bg-green-50 px-4 py-3">
          <p className="text-xs text-gray-500">待審核</p>
          <p className="text-2xl font-bold text-green-600">
            {statusCounts.submitted}
          </p>
        </div>
        <div className="rounded-lg border bg-blue-50 px-4 py-3">
          <p className="text-xs text-gray-500">已審核</p>
          <p className="text-2xl font-bold text-blue-600">
            {statusCounts.approved}
          </p>
        </div>
        <div className="rounded-lg border bg-red-50 px-4 py-3">
          <p className="text-xs text-gray-500">已退回</p>
          <p className="text-2xl font-bold text-red-600">
            {statusCounts.rejected}
          </p>
        </div>
        <div className="rounded-lg border bg-yellow-50 px-4 py-3">
          <p className="text-xs text-gray-500">未繳交</p>
          <p className="text-2xl font-bold text-yellow-600">
            {statusCounts.pending}
          </p>
        </div>
      </div>

      {/* Reject Modal */}
      {rejectingTeam !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-3 text-lg font-semibold">退回留用名單</h3>
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
                  className={`rounded-lg border p-4 ${cfg.border} ${cfg.bg}`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
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
                          繳交時間：{new Date(s.submitted_at).toLocaleString("zh-TW")}
                        </p>
                      )}
                      {status === "rejected" && s.commissioner_notes && (
                        <p className="mt-1 text-xs text-red-600">
                          退回原因：{s.commissioner_notes}
                        </p>
                      )}
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2">
                      {s.is_submitted && (
                        <button
                          onClick={() => handleExpand(s.team_id)}
                          className="rounded border bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-50"
                        >
                          {isExpanded ? "收合" : "查看詳情"}
                        </button>
                      )}

                      {status === "submitted" && (
                        <>
                          <button
                            onClick={() => handleApprove(s.team_id)}
                            className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-500"
                          >
                            審核通過
                          </button>
                          <button
                            onClick={() => handleRejectStart(s.team_id)}
                            className="rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-500"
                          >
                            退回
                          </button>
                        </>
                      )}

                      {status === "approved" && (
                        <button
                          onClick={() => handleUnlock(s.team_id, s.manager_name)}
                          className="rounded border border-yellow-400 bg-yellow-50 px-3 py-1 text-xs text-yellow-700 hover:bg-yellow-100"
                        >
                          解鎖
                        </button>
                      )}

                      {status === "pending" && (
                        <Link
                          href={`/${selectedYear}/${s.team_id}`}
                          className="rounded border bg-white px-3 py-1 text-xs text-indigo-600 hover:bg-indigo-50"
                        >
                          查看名單
                        </Link>
                      )}
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
                          <h4 className="mb-2 text-sm font-semibold">留用選擇</h4>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                                  <th className="px-3 py-2">球員</th>
                                  <th className="px-3 py-2">現約</th>
                                  <th className="px-3 py-2">操作</th>
                                  <th className="px-3 py-2">新約</th>
                                </tr>
                              </thead>
                              <tbody>
                                {detail.selections.map((sel) => (
                                  <tr
                                    key={sel.player_name}
                                    className="border-b last:border-0"
                                  >
                                    <td className="px-3 py-1.5">{sel.player_name}</td>
                                    <td className="px-3 py-1.5 font-mono text-xs">
                                      {sel.current_contract}
                                    </td>
                                    <td className="px-3 py-1.5">
                                      <span
                                        className={`rounded px-1.5 py-0.5 text-xs ${
                                          sel.action === "release"
                                            ? "bg-red-100 text-red-700"
                                            : sel.action === "keep"
                                              ? "bg-green-100 text-green-700"
                                              : sel.action === "rookie"
                                                ? "bg-purple-100 text-purple-700"
                                                : sel.action.startsWith("extend")
                                                  ? "bg-blue-100 text-blue-700"
                                                  : "bg-gray-100 text-gray-700"
                                        }`}
                                      >
                                        {sel.action === "keep"
                                          ? "保留"
                                          : sel.action === "release"
                                            ? "釋出"
                                            : sel.action === "rookie"
                                              ? "新人約"
                                              : sel.action.startsWith("extend")
                                                ? `延長 ${sel.extension_years} 年`
                                                : sel.action}
                                      </span>
                                    </td>
                                    <td className="px-3 py-1.5 font-mono text-xs">
                                      {sel.next_contract || "-"}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>

                        {/* Financial summary */}
                        {detail.validation_result?.financial_summary && (
                          <div>
                            <h4 className="mb-2 text-sm font-semibold">財務摘要</h4>
                            <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                              {(() => {
                                const f = detail.validation_result.financial_summary;
                                return (
                                  <>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">薪資上限</p>
                                      <p className="font-semibold">${f.salary_cap}</p>
                                    </div>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">留用成本</p>
                                      <p className="font-semibold">${f.keeper_cost}</p>
                                    </div>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">可用薪資</p>
                                      <p className="font-semibold">${f.available_salary}</p>
                                    </div>
                                    <div className="rounded bg-gray-50 p-2">
                                      <p className="text-xs text-gray-500">
                                        留用人數 (主力/板凳)
                                      </p>
                                      <p className="font-semibold">
                                        {f.active_keeper_count} / {f.bench_keeper_count}
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
                                  驗證錯誤
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
                                  警告
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
                                  驗證通過，無錯誤或警告。
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
