"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSubmissions, getYears, approveSubmission } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { SubmissionStatus } from "@/types";

export default function CommissionerDashboard() {
  const { user } = useAuth();
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number>(
    new Date().getFullYear(),
  );
  const [submissions, setSubmissions] = useState<SubmissionStatus[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getYears().then((y) => {
      setYears(y);
      if (y.length > 0 && !y.includes(selectedYear)) {
        setSelectedYear(y[y.length - 1]);
      }
    });
  }, []);

  useEffect(() => {
    if (!selectedYear || !user?.is_commissioner) return;
    setLoading(true);
    getSubmissions(selectedYear)
      .then(setSubmissions)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedYear, user]);

  const handleApprove = async (teamId: number, approved: boolean) => {
    try {
      await approveSubmission(selectedYear, teamId, approved);
      // Refresh
      const updated = await getSubmissions(selectedYear);
      setSubmissions(updated);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed");
    }
  };

  if (!user?.is_commissioner) {
    return (
      <div className="py-10 text-center text-red-600">
        需要 Commissioner 權限才能存取此頁面。
      </div>
    );
  }

  const submitted = submissions.filter((s) => s.is_submitted);
  const pending = submissions.filter((s) => !s.is_submitted);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Commissioner 管理面板</h1>
        <div className="flex items-center gap-4">
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
            href="/commissioner/import"
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500"
          >
            匯入 Excel
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-6 flex gap-4">
        <div className="rounded-lg border bg-white px-4 py-3">
          <p className="text-xs text-gray-500">總隊伍</p>
          <p className="text-2xl font-bold">{submissions.length}</p>
        </div>
        <div className="rounded-lg border bg-green-50 px-4 py-3">
          <p className="text-xs text-gray-500">已繳交</p>
          <p className="text-2xl font-bold text-green-600">
            {submitted.length}
          </p>
        </div>
        <div className="rounded-lg border bg-yellow-50 px-4 py-3">
          <p className="text-xs text-gray-500">未繳交</p>
          <p className="text-2xl font-bold text-yellow-600">
            {pending.length}
          </p>
        </div>
        <div className="rounded-lg border bg-blue-50 px-4 py-3">
          <p className="text-xs text-gray-500">已審核</p>
          <p className="text-2xl font-bold text-blue-600">
            {submitted.filter((s) => s.commissioner_approved).length}
          </p>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
          {submissions.map((s) => (
            <div
              key={s.team_id}
              className={`rounded-lg border p-4 ${
                s.commissioner_approved
                  ? "border-blue-200 bg-blue-50"
                  : s.is_submitted
                    ? "border-green-200 bg-green-50"
                    : "border-gray-200 bg-white"
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <h3 className="font-semibold">{s.manager_name}</h3>
                {s.commissioner_approved ? (
                  <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">
                    已審核
                  </span>
                ) : s.is_submitted ? (
                  <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">
                    已繳交
                  </span>
                ) : (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                    未繳交
                  </span>
                )}
              </div>
              {s.team_name && (
                <p className="mb-2 text-xs text-gray-500">{s.team_name}</p>
              )}
              {s.submitted_at && (
                <p className="mb-2 text-xs text-gray-400">
                  {new Date(s.submitted_at).toLocaleDateString()}
                </p>
              )}

              <div className="flex gap-2">
                <Link
                  href={`/${selectedYear}/${s.team_id}`}
                  className="text-xs text-indigo-600 hover:underline"
                >
                  查看
                </Link>
                {s.is_submitted && !s.commissioner_approved && (
                  <button
                    onClick={() => handleApprove(s.team_id, true)}
                    className="text-xs text-green-600 hover:underline"
                  >
                    審核通過
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
