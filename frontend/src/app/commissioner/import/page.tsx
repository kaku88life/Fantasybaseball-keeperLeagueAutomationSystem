"use client";

import { useCallback, useState } from "react";
import { useAuth } from "@/lib/auth";
import { importExcel } from "@/lib/api";

export default function ImportExcelPage() {
  const { user } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [year, setYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    year: number;
    teams_count: number;
    teams: string[];
    message: string;
  } | null>(null);
  const [error, setError] = useState("");

  const handleImport = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await importExcel(file, year);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }, [file, year]);

  if (!user?.is_commissioner) {
    return (
      <div className="py-10 text-center text-red-600">
        需要 Commissioner 權限才能存取此頁面。
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="mb-6 text-2xl font-bold">匯入 Excel</h1>

      <div className="space-y-4 rounded-lg border bg-white p-6">
        <div>
          <label className="mb-1 block text-sm font-medium">年份</label>
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
            min={2020}
            max={2030}
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">
            Excel 檔案 (.xlsx)
          </label>
          <input
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="w-full rounded border px-3 py-2"
          />
          <p className="mt-1 text-xs text-gray-400">
            上傳包含各隊名單與合約資料的 Excel 檔案
          </p>
        </div>

        <button
          onClick={handleImport}
          disabled={!file || loading}
          className="w-full rounded bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "匯入中..." : "開始匯入"}
        </button>

        {error && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded border border-green-200 bg-green-50 p-3">
            <p className="mb-2 font-medium text-green-800">{result.message}</p>
            <p className="text-sm text-green-700">
              已匯入 {result.teams_count} 隊:
            </p>
            <ul className="mt-1 list-inside list-disc text-sm text-green-600">
              {result.teams.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
