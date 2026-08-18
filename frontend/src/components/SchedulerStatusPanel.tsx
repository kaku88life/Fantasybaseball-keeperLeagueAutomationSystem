"use client";

/**
 * Scheduler diagnostics panel for the Commissioner page.
 *
 * Renders live data from GET /api/commissioner/scheduler/status:
 * - running state + timezone + misfire grace
 * - per-job next run / latest outcome / last success
 * - recent scheduler_job_runs timeline with a failures-only filter
 *
 * This panel exists because the 2026-07-27 Yahoo token outage ran silently
 * for 22 days: the data was in scheduler_job_runs the whole time but nothing
 * displayed it.
 */

import { useState } from "react";
import useSWR from "swr";

import { getSchedulerStatus, type SchedulerJobRun } from "@/lib/api";

/** Chinese labels for known job ids; unknown ids fall back to the raw id. */
const JOB_LABELS: Record<string, string> = {
  transaction_fetch: "Yahoo 交易紀錄（每日 00:15）",
  roster_snapshot_rebuild: "名冊＋快照＋ownership 同步（每日 00:30）",
  player_status_update: "球員狀態 IL/DTD/NA（每日 12:30）",
  ar_rank_refresh: "AR-Rank＋球季數據（每日 18:00）",
  statcast_sync: "Statcast 逐球資料（每日 19:30）",
  war_report: "週戰報（每週一 21:00）",
  monthly_report: "月報（每月 1 日 20:45）",
  keeper_reminder: "留用催繳提醒",
  rookie_monitor: "新秀升上大聯盟監控",
  startup_refresh: "啟動時交易重抓",
  scheduler: "排程器本身",
};

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "-";
  return d.toLocaleString("zh-TW", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function hoursSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (isNaN(t)) return null;
  return (Date.now() - t) / 3_600_000;
}

function StatusBadgeChip({ status }: { status: string }) {
  const styles: Record<string, string> = {
    success: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    started: "bg-blue-100 text-blue-700",
    skipped: "bg-gray-100 text-gray-500",
  };
  const labels: Record<string, string> = {
    success: "成功",
    failed: "失敗",
    started: "執行中",
    skipped: "略過",
  };
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-gray-100 text-gray-500"}`}
    >
      {labels[status] ?? status}
    </span>
  );
}

/** Freshness card: colors by how overdue a daily/weekly job's last success is. */
function FreshnessCard({
  label,
  lastSuccess,
  cadenceHours,
}: {
  label: string;
  lastSuccess: string | null;
  cadenceHours: number;
}) {
  const age = hoursSince(lastSuccess);
  // green: within 1.5 cadences; yellow: within 3; red: beyond (or unknown)
  const tone =
    age !== null && age <= cadenceHours * 1.5
      ? "green"
      : age !== null && age <= cadenceHours * 3
        ? "yellow"
        : "red";
  const toneCls = {
    green: "border-green-200 bg-green-50",
    yellow: "border-amber-200 bg-amber-50",
    red: "border-red-200 bg-red-50",
  }[tone];
  const textCls = {
    green: "text-green-800",
    yellow: "text-amber-800",
    red: "text-red-800",
  }[tone];
  return (
    <div className={`rounded-lg border p-3 ${toneCls}`}>
      <p className="text-xs font-semibold text-gray-600">{label}</p>
      <p className={`mt-1 text-sm font-bold ${textCls}`}>
        {lastSuccess ? fmtTime(lastSuccess) : "近 100 筆內無成功紀錄"}
      </p>
      {age !== null && (
        <p className={`mt-0.5 text-xs ${textCls}`}>
          {age < 48
            ? `${Math.round(age)} 小時前`
            : `${Math.round(age / 24)} 天前`}
        </p>
      )}
    </div>
  );
}

export default function SchedulerStatusPanel() {
  const [failedOnly, setFailedOnly] = useState(false);
  const { data, error, isLoading, mutate } = useSWR(
    "scheduler-status",
    () => getSchedulerStatus(100),
    { revalidateOnFocus: false },
  );

  if (isLoading) {
    return (
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        排程狀態載入中...
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        排程狀態載入失敗：{error instanceof Error ? error.message : "未知錯誤"}
      </div>
    );
  }

  const runs = data.recent_runs ?? [];

  // Latest run + last success per job, derived from the (newest-first) run log
  const latestByJob = new Map<string, SchedulerJobRun>();
  const lastSuccessByJob = new Map<string, SchedulerJobRun>();
  for (const r of runs) {
    if (!latestByJob.has(r.job_id)) latestByJob.set(r.job_id, r);
    if (r.status === "success" && !lastSuccessByJob.has(r.job_id)) {
      lastSuccessByJob.set(r.job_id, r);
    }
  }

  const visibleRuns = (failedOnly ? runs.filter((r) => r.status === "failed") : runs).slice(0, 20);

  return (
    <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-bold text-gray-900">
          排程狀態 <span className="text-sm font-medium text-gray-400">Scheduler Status</span>
        </h2>
        {data.running ? (
          <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-700">
            運作中 Running
          </span>
        ) : (
          <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700">
            未運作 Stopped{data.reason ? `：${data.reason}` : ""}
          </span>
        )}
        <button
          onClick={() => mutate()}
          className="ml-auto rounded border border-gray-300 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50"
        >
          重新整理
        </button>
      </div>
      <p className="mt-1 text-xs text-gray-500">
        時區 {data.timezone ?? "-"}　遲到容忍{" "}
        {data.misfire_grace_seconds ? `${data.misfire_grace_seconds / 3600} 小時` : "-"}
        {data.recent_runs_error && (
          <span className="text-red-600">　執行紀錄讀取失敗：{data.recent_runs_error}</span>
        )}
      </p>

      {/* Freshness summary: the three feeds users actually notice going stale */}
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <FreshnessCard
          label="名冊同步 Roster Sync"
          lastSuccess={lastSuccessByJob.get("roster_snapshot_rebuild")?.recorded_at ?? null}
          cadenceHours={24}
        />
        <FreshnessCard
          label="球員數據 AR-Rank"
          lastSuccess={lastSuccessByJob.get("ar_rank_refresh")?.recorded_at ?? null}
          cadenceHours={24}
        />
        <FreshnessCard
          label="週戰報 War Report"
          lastSuccess={lastSuccessByJob.get("war_report")?.recorded_at ?? null}
          cadenceHours={168}
        />
      </div>

      {/* Jobs table */}
      <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">工作</th>
              <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">下次執行</th>
              <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">最近一次結果</th>
              <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">最近成功</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {data.jobs.map((job) => {
              const latest = latestByJob.get(job.id);
              const lastOk = lastSuccessByJob.get(job.id);
              return (
                <tr key={job.id}>
                  <td className="px-3 py-2">
                    <p className="font-medium text-gray-900">{job.id}</p>
                    <p className="text-xs text-gray-400">{JOB_LABELS[job.id] ?? job.trigger}</p>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-gray-700">
                    {fmtTime(job.next_run_time)}
                  </td>
                  <td className="px-3 py-2">
                    {latest ? (
                      <div>
                        <StatusBadgeChip status={latest.status} />
                        {latest.status === "failed" && latest.detail && (
                          <p className="mt-1 max-w-xs whitespace-normal break-words text-xs text-red-600">
                            {latest.detail}
                          </p>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400">無紀錄</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-gray-700">
                    {lastOk ? fmtTime(lastOk.recorded_at) : "-"}
                  </td>
                </tr>
              );
            })}
            {data.jobs.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-center text-sm text-gray-400">
                  沒有已註冊的排程工作
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Recent runs timeline */}
      <div className="mt-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-800">
            近期執行紀錄 <span className="text-xs font-medium text-gray-400">Recent Runs</span>
          </h3>
          <button
            onClick={() => setFailedOnly((v) => !v)}
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              failedOnly ? "bg-red-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            只看失敗
          </button>
        </div>
        <ul className="mt-2 divide-y divide-gray-100">
          {visibleRuns.map((r, i) => (
            <li key={`${r.job_id}-${r.recorded_at}-${i}`} className="flex flex-wrap items-baseline gap-2 py-1.5 text-sm">
              <span className="w-28 shrink-0 text-xs text-gray-500">{fmtTime(r.recorded_at)}</span>
              <StatusBadgeChip status={r.status} />
              <span className="font-medium text-gray-800">{r.job_id}</span>
              {r.detail && (
                <span
                  className={`w-full break-words pl-0 text-xs sm:w-auto sm:pl-0 ${
                    r.status === "failed" ? "text-red-600" : "text-gray-500"
                  }`}
                >
                  {r.detail}
                </span>
              )}
            </li>
          ))}
          {visibleRuns.length === 0 && (
            <li className="py-2 text-sm text-gray-400">
              {failedOnly ? "近期沒有失敗紀錄" : "沒有執行紀錄"}
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
