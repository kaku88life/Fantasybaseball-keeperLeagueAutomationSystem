"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  getAllBuyouts,
  createBuyout,
  updateBuyout,
  deleteBuyout,
  getYears,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { BuyoutRecord } from "@/types";

// Team list for dropdown selection
const TEAMS = [
  { id: 1, name: "Kaku" },
  { id: 2, name: "Hyper" },
  { id: 3, name: "TIMMY LIU" },
  { id: 4, name: "Hank" },
  { id: 5, name: "Tony" },
  { id: 6, name: "Billy" },
  { id: 7, name: "EDDIE" },
  { id: 8, name: "rawstuff" },
  { id: 9, name: "YWC" },
  { id: 10, name: "wei" },
  { id: 11, name: "Ponpon" },
  { id: 12, name: "Javier" },
  { id: 13, name: "James Chen" },
  { id: 14, name: "Leo" },
  { id: 15, name: "Yu-Che Chang" },
  { id: 16, name: "TIMMY" },
];

interface BuyoutFormData {
  team_id: number;
  year: number;
  player_name: string;
  original_contract: string;
  buyout_salary: number;
  buyout_faab: number;
  buyout_years: number;
  remaining_years: number;
  buyout_type: "mid_season_drop" | "keeper_release";
  use_faab: boolean;
  notes: string;
}

const EMPTY_FORM: BuyoutFormData = {
  team_id: 0,
  year: 2026,
  player_name: "",
  original_contract: "",
  buyout_salary: 0,
  buyout_faab: 0,
  buyout_years: 1,
  remaining_years: 1,
  buyout_type: "mid_season_drop",
  use_faab: false,
  notes: "",
};

export default function BuyoutsPage() {
  const { user, loading: authLoading } = useAuth();
  const [years, setYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number>(2026);
  const [buyouts, setBuyouts] = useState<(BuyoutRecord & { manager_name: string })[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<BuyoutFormData>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [teams, setTeams] = useState<{ id: number; name: string }[]>(TEAMS);

  // Load available years
  useEffect(() => {
    getYears().then((yrs) => {
      if (yrs.length > 0) {
        setYears(yrs);
        setSelectedYear(Math.max(...yrs));
      }
    }).catch(() => {});
  }, []);

  // Load teams from API
  useEffect(() => {
    import("@/lib/api").then(({ getTeams }) => {
      getTeams().then((t: Array<{ id: number; manager_name: string }>) => {
        if (t.length > 0) {
          setTeams(t.map((tm) => ({ id: tm.id, name: tm.manager_name })));
        }
      }).catch(() => {});
    });
  }, []);

  const loadBuyouts = useCallback(async () => {
    if (!selectedYear) return;
    setLoading(true);
    try {
      const result = await getAllBuyouts(selectedYear);
      setBuyouts(result.buyouts || []);
    } catch {
      setBuyouts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedYear]);

  useEffect(() => {
    if (user?.is_commissioner) {
      loadBuyouts();
    }
  }, [user, loadBuyouts]);

  const handleSubmit = async () => {
    setError("");
    setSuccess("");

    if (!form.team_id || !form.player_name || !form.buyout_salary) {
      setError("Please fill in team, player name, and buyout salary");
      return;
    }

    setSaving(true);
    try {
      if (editingId) {
        await updateBuyout(editingId, {
          player_name: form.player_name,
          original_contract: form.original_contract,
          buyout_salary: form.buyout_salary,
          buyout_faab: form.buyout_faab,
          buyout_years: form.buyout_years,
          remaining_years: form.remaining_years,
          buyout_type: form.buyout_type,
          use_faab: form.use_faab,
          notes: form.notes,
        });
        setSuccess("Buyout record updated");
      } else {
        await createBuyout(form);
        setSuccess("Buyout record created");
      }
      setShowForm(false);
      setEditingId(null);
      setForm({ ...EMPTY_FORM, year: selectedYear });
      loadBuyouts();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (bo: BuyoutRecord & { manager_name: string }) => {
    setEditingId(bo.id || null);
    setForm({
      team_id: bo.team_id || 0,
      year: bo.year || selectedYear,
      player_name: bo.player_name,
      original_contract: bo.original_contract,
      buyout_salary: bo.buyout_salary || bo.buyout_salary_cost || 0,
      buyout_faab: bo.buyout_faab || bo.buyout_faab_cost || 0,
      buyout_years: bo.buyout_years || bo.remaining_years,
      remaining_years: bo.remaining_years,
      buyout_type: (bo.buyout_type as "mid_season_drop" | "keeper_release") || "keeper_release",
      use_faab: bo.use_faab,
      notes: bo.notes || bo.note || "",
    });
    setShowForm(true);
    setError("");
    setSuccess("");
  };

  const handleDelete = async (id: number, playerName: string) => {
    if (!confirm(`Confirm delete buyout record: ${playerName}?`)) return;
    try {
      await deleteBuyout(id);
      setSuccess(`Buyout deleted: ${playerName}`);
      loadBuyouts();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const handleUseFaabChange = (checked: boolean) => {
    const salary = form.buyout_salary;
    if (checked && salary > 0) {
      setForm({
        ...form,
        use_faab: true,
        buyout_faab: Math.ceil(salary / 2),
        buyout_salary: Math.floor(salary / 2),
      });
    } else {
      setForm({
        ...form,
        use_faab: false,
        buyout_faab: 0,
      });
    }
  };

  // Auth check
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (!user?.is_commissioner) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Access restricted</h1>
          <p className="text-gray-500">Commissioner permission required</p>
          <Link href="/" className="text-blue-600 hover:underline mt-4 inline-block">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-6xl px-2 py-4 sm:px-4 sm:py-8">
        {/* Header */}
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">買斷管理 Buyout</h1>
            <p className="mt-1 text-xs text-gray-500 sm:text-sm">
              管理合約買斷紀錄（季中釋出 / 留用階段買斷）
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/commissioner"
              className="text-sm text-blue-600 hover:underline"
            >
              返回管理面板
            </Link>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
              {!years.includes(selectedYear) && (
                <option value={selectedYear}>{selectedYear}</option>
              )}
            </select>
          </div>
        </div>

        {/* Messages */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded-lg text-sm">
            {success}
          </div>
        )}

        {/* Add Buyout Button */}
        <div className="mb-6">
          <button
            onClick={() => {
              setShowForm(true);
              setEditingId(null);
              setForm({ ...EMPTY_FORM, year: selectedYear });
              setError("");
              setSuccess("");
            }}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-indigo-500 transition-colors"
          >
            + 新增買斷紀錄
          </button>
        </div>

        {/* Create/Edit Form */}
        {showForm && (
          <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
            <h2 className="mb-4 text-base font-semibold text-gray-900 sm:text-lg">
              {editingId ? "編輯買斷" : "新增買斷紀錄"}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Team */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Team
                </label>
                <select
                  value={form.team_id}
                  onChange={(e) => setForm({ ...form, team_id: Number(e.target.value) })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  disabled={!!editingId}
                >
                  <option value={0}>-- Select team --</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Player Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Player Name
                </label>
                <input
                  type="text"
                  value={form.player_name}
                  onChange={(e) => setForm({ ...form, player_name: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. Justin Steele"
                />
              </div>

              {/* Original Contract */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Original Contract
                </label>
                <input
                  type="text"
                  value={form.original_contract}
                  onChange={(e) => setForm({ ...form, original_contract: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. $6/N1"
                />
              </div>

              {/* Buyout Type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Buyout Type
                </label>
                <select
                  value={form.buyout_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      buyout_type: e.target.value as "mid_season_drop" | "keeper_release",
                    })
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="mid_season_drop">Mid-season Drop</option>
                  <option value="keeper_release">Keeper Release</option>
                </select>
              </div>

              {/* Per-year Salary (full, before FAAB split) */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Per-year Salary ${form.use_faab ? "(auto-calculated)" : ""}
                </label>
                <input
                  type="number"
                  min={0}
                  value={form.use_faab ? form.buyout_salary + form.buyout_faab : form.buyout_salary}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    if (form.use_faab) {
                      setForm({
                        ...form,
                        buyout_salary: Math.floor(val / 2),
                        buyout_faab: Math.ceil(val / 2),
                      });
                    } else {
                      setForm({ ...form, buyout_salary: val });
                    }
                  }}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. 6"
                />
              </div>

              {/* FAAB Split Toggle */}
              <div className="flex items-end pb-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.use_faab}
                    onChange={(e) => handleUseFaabChange(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700">
                    FAAB Split (FAAB: ${form.buyout_faab} / Cap: ${form.buyout_salary})
                  </span>
                </label>
              </div>

              {/* Buyout Years */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Total Buyout Years
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={form.buyout_years}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setForm({
                      ...form,
                      buyout_years: val,
                      remaining_years: Math.min(form.remaining_years, val),
                    });
                  }}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Remaining Years */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Remaining Years
                </label>
                <input
                  type="number"
                  min={1}
                  max={form.buyout_years}
                  value={form.remaining_years}
                  onChange={(e) =>
                    setForm({ ...form, remaining_years: Number(e.target.value) })
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Notes */}
              <div className="md:col-span-2 lg:col-span-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Notes
                </label>
                <input
                  type="text"
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. 2025 mid-season drop"
                />
              </div>
            </div>

            {/* Summary */}
            <div className="mt-4 p-3 bg-gray-50 rounded-lg text-sm text-gray-600">
              <strong>Summary:</strong>{" "}
              {form.player_name || "(player)"} - {form.original_contract || "(contract)"} |{" "}
              {form.use_faab ? (
                <>Cap ${form.buyout_salary}/yr + FAAB ${form.buyout_faab}/yr</>
              ) : (
                <>Cap ${form.buyout_salary}/yr</>
              )}{" "}
              x {form.remaining_years} year(s) remaining
            </div>

            {/* Buttons */}
            <div className="mt-4 flex gap-3">
              <button
                onClick={handleSubmit}
                disabled={saving}
                className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-indigo-500 disabled:opacity-50 transition-colors"
              >
                {saving ? "Saving..." : editingId ? "Update" : "Create"}
              </button>
              <button
                onClick={() => {
                  setShowForm(false);
                  setEditingId(null);
                  setForm({ ...EMPTY_FORM, year: selectedYear });
                }}
                className="border border-gray-300 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Buyout Records Table */}
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
          <div className="border-b border-gray-200 px-4 py-4 sm:px-6">
            <h2 className="text-base font-semibold text-gray-900 sm:text-lg">
              {selectedYear} 年買斷紀錄
            </h2>
            <p className="mt-1 text-xs text-gray-500 sm:text-sm">
              共 {buyouts.length} 筆 |{" "}
              薪資帽影響: $
              {buyouts.reduce((sum, b) => sum + (b.buyout_salary || b.buyout_salary_cost || 0), 0)} |{" "}
              FAAB 影響: $
              {buyouts.reduce((sum, b) => sum + (b.buyout_faab || b.buyout_faab_cost || 0), 0)}
            </p>
          </div>

          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          ) : buyouts.length === 0 ? (
            <div className="p-8 text-center text-gray-400">
              No buyout records for {selectedYear}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-3 py-3 text-left font-medium sm:px-4">隊伍</th>
                    <th className="px-3 py-3 text-left font-medium sm:px-4">球員</th>
                    <th className="hidden px-4 py-3 text-left font-medium sm:table-cell">合約</th>
                    <th className="hidden px-4 py-3 text-left font-medium md:table-cell">類型</th>
                    <th className="px-3 py-3 text-right font-medium sm:px-4">薪資/年</th>
                    <th className="hidden px-4 py-3 text-right font-medium sm:table-cell">FAAB/年</th>
                    <th className="px-3 py-3 text-center font-medium sm:px-4">剩餘</th>
                    <th className="hidden px-4 py-3 text-left font-medium lg:table-cell">備註</th>
                    <th className="px-3 py-3 text-center font-medium sm:px-4">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {buyouts.map((bo) => (
                    <tr key={bo.id} className="hover:bg-gray-50">
                      <td className="px-3 py-3 font-medium text-gray-900 sm:px-4">
                        {bo.manager_name}
                      </td>
                      <td className="px-3 py-3 text-gray-700 sm:px-4">{bo.player_name}</td>
                      <td className="hidden px-4 py-3 font-mono text-xs text-gray-500 sm:table-cell">
                        {bo.original_contract}
                      </td>
                      <td className="hidden px-4 py-3 md:table-cell">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            bo.buyout_type === "mid_season_drop"
                              ? "bg-orange-100 text-orange-700"
                              : "bg-purple-100 text-purple-700"
                          }`}
                        >
                          {bo.buyout_type === "mid_season_drop"
                            ? "季中釋出"
                            : "留用買斷"}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-gray-900 sm:px-4">
                        ${bo.buyout_salary || bo.buyout_salary_cost || 0}
                      </td>
                      <td className="hidden px-4 py-3 text-right font-mono text-gray-500 sm:table-cell">
                        {(bo.buyout_faab || bo.buyout_faab_cost || 0) > 0
                          ? `$${bo.buyout_faab || bo.buyout_faab_cost}`
                          : "-"}
                      </td>
                      <td className="px-3 py-3 text-center sm:px-4">
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
                          {bo.remaining_years} 年
                        </span>
                      </td>
                      <td className="hidden px-4 py-3 text-xs text-gray-500 max-w-[200px] truncate lg:table-cell">
                        {bo.notes || bo.note || "-"}
                      </td>
                      <td className="px-3 py-3 text-center sm:px-4">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => handleEdit(bo)}
                            className="min-h-[44px] min-w-[44px] rounded px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 hover:text-blue-800 transition-colors sm:min-h-0 sm:min-w-0"
                          >
                            編輯
                          </button>
                          <button
                            onClick={() =>
                              bo.id && handleDelete(bo.id, bo.player_name)
                            }
                            className="min-h-[44px] min-w-[44px] rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50 hover:text-red-800 transition-colors sm:min-h-0 sm:min-w-0"
                          >
                            刪除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Per-team Summary */}
        {buyouts.length > 0 && (
          <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:p-6">
            <h2 className="mb-4 text-base font-semibold text-gray-900 sm:text-lg">
              各隊買斷摘要
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(
                buyouts.reduce(
                  (acc, bo) => {
                    const key = bo.manager_name || "Unknown";
                    if (!acc[key]) acc[key] = { cap: 0, faab: 0, count: 0 };
                    acc[key].cap += bo.buyout_salary || bo.buyout_salary_cost || 0;
                    acc[key].faab += bo.buyout_faab || bo.buyout_faab_cost || 0;
                    acc[key].count += 1;
                    return acc;
                  },
                  {} as Record<string, { cap: number; faab: number; count: number }>,
                ),
              )
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([name, summary]) => (
                  <div
                    key={name}
                    className="border border-gray-200 rounded-lg p-3 flex justify-between items-center"
                  >
                    <div>
                      <p className="font-medium text-gray-900">{name}</p>
                      <p className="text-xs text-gray-500">
                        {summary.count} buyout(s)
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm text-gray-900">
                        Cap: -${summary.cap}
                      </p>
                      {summary.faab > 0 && (
                        <p className="font-mono text-xs text-gray-500">
                          FAAB: -${summary.faab}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
