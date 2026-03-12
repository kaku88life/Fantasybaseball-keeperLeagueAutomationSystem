"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getUsers,
  getTeams,
  assignTeam,
  setCommissioner,
  updateUserLineName,
  deleteUser,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UserWithTeam, DBTeam } from "@/types";

export default function UserManagementPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<UserWithTeam[]>([]);
  const [teams, setTeams] = useState<DBTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  // LINE name editing state
  const [editingLineName, setEditingLineName] = useState<number | null>(null);
  const [lineNameInput, setLineNameInput] = useState("");

  const refresh = async () => {
    setLoading(true);
    try {
      const [u, t] = await Promise.all([getUsers(), getTeams()]);
      setUsers(u);
      setTeams(t);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.is_commissioner) refresh();
  }, [user]);

  const handleAssignTeam = async (userId: number, teamId: number) => {
    setSaving(userId);
    try {
      await assignTeam(userId, teamId);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setSaving(null);
    }
  };

  const handleSetCommissioner = async (userId: number, nickname: string) => {
    if (!confirm(`確定要授予 ${nickname} Commissioner 權限？`)) return;
    try {
      await setCommissioner(userId);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    }
  };

  const handleClearLineName = async (userId: number, currentName: string) => {
    if (!confirm(`確定要清除 "${currentName}" 的 LINE 名稱？`)) return;
    setSaving(userId);
    try {
      await updateUserLineName(userId, "");
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setSaving(null);
    }
  };

  const handleSaveLineName = async (userId: number) => {
    setSaving(userId);
    try {
      await updateUserLineName(userId, lineNameInput);
      setEditingLineName(null);
      setLineNameInput("");
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setSaving(null);
    }
  };

  const handleDeleteUser = async (u: UserWithTeam) => {
    const name = u.yahoo_nickname || u.line_name || `#${u.id}`;
    if (!confirm(`確定要刪除用戶 "${name}"？此操作無法復原。用戶下次登入會重新建立帳號。`)) return;
    setSaving(u.id);
    try {
      await deleteUser(u.id);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "操作失敗");
    } finally {
      setSaving(null);
    }
  };

  if (!user?.is_commissioner) {
    return (
      <div className="py-10 text-center text-red-600">
        需要 Commissioner 權限才能存取此頁面。
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">用戶管理 User Management</h1>
        <Link
          href="/commissioner"
          className="rounded border px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          返回管理面板 Back to Dashboard
        </Link>
      </div>

      {loading ? (
        <p className="text-gray-500">載入中...</p>
      ) : users.length === 0 ? (
        <p className="text-gray-500">目前沒有已登入的用戶。</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs text-gray-500">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Yahoo 暱稱 Nickname</th>
                <th className="px-4 py-3">LINE 名稱</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Yahoo GUID</th>
                <th className="px-4 py-3">對應隊伍 Team</th>
                <th className="px-4 py-3">最後登入 Last Login</th>
                <th className="px-4 py-3">Commissioner</th>
                <th className="px-4 py-3">操作 Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-3 text-xs text-gray-400">#{u.id}</td>
                  <td className="px-4 py-3 font-medium">{u.yahoo_nickname || "-"}</td>
                  <td className="px-4 py-3">
                    {editingLineName === u.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          type="text"
                          value={lineNameInput}
                          onChange={(e) => setLineNameInput(e.target.value)}
                          className="w-24 rounded border px-2 py-0.5 text-xs"
                          placeholder="LINE 名稱"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveLineName(u.id);
                            if (e.key === "Escape") {
                              setEditingLineName(null);
                              setLineNameInput("");
                            }
                          }}
                        />
                        <button
                          onClick={() => handleSaveLineName(u.id)}
                          disabled={saving === u.id}
                          className="rounded bg-green-600 px-1.5 py-0.5 text-xs text-white hover:bg-green-700"
                        >
                          OK
                        </button>
                        <button
                          onClick={() => {
                            setEditingLineName(null);
                            setLineNameInput("");
                          }}
                          className="rounded px-1.5 py-0.5 text-xs text-gray-500 hover:bg-gray-200"
                        >
                          取消
                        </button>
                      </div>
                    ) : u.line_name ? (
                      <div className="flex items-center gap-1">
                        <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                          {u.line_name}
                        </span>
                        <button
                          onClick={() => {
                            setEditingLineName(u.id);
                            setLineNameInput(u.line_name || "");
                          }}
                          className="rounded p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
                          title="編輯 LINE 名稱"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                            <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleClearLineName(u.id, u.line_name || "")}
                          disabled={saving === u.id}
                          className="rounded p-0.5 text-gray-400 hover:bg-red-100 hover:text-red-600"
                          title="清除 LINE 名稱"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                          </svg>
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => {
                          setEditingLineName(u.id);
                          setLineNameInput("");
                        }}
                        className="text-xs text-gray-400 hover:text-indigo-600"
                      >
                        + 設定
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{u.yahoo_email || "-"}</td>
                  <td className="px-4 py-3">
                    {u.yahoo_guid ? (
                      <span
                        className="cursor-help font-mono text-xs text-gray-400"
                        title={u.yahoo_guid}
                      >
                        {u.yahoo_guid.slice(0, 8)}...
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={u.team_id ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val) handleAssignTeam(u.id, Number(val));
                      }}
                      disabled={saving === u.id}
                      className="rounded border px-2 py-1 text-sm"
                    >
                      <option value="">-- 未指派 --</option>
                      {teams.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.manager_name}
                        </option>
                      ))}
                    </select>
                    {saving === u.id && (
                      <span className="ml-2 text-xs text-gray-400">儲存中...</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {u.last_login
                      ? new Date(u.last_login).toLocaleString("zh-TW")
                      : "-"}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_commissioner ? (
                      <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700">
                        Commissioner
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {!u.is_commissioner && (
                        <button
                          onClick={() =>
                            handleSetCommissioner(u.id, u.yahoo_nickname || `#${u.id}`)
                          }
                          className="rounded border px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50"
                        >
                          授予權限 Grant
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteUser(u)}
                        disabled={saving === u.id || u.id === user?.user_id}
                        className="rounded border border-red-200 px-2 py-1 text-xs text-red-500 hover:bg-red-50 disabled:opacity-30"
                        title={u.id === user?.user_id ? "無法刪除自己的帳號" : "刪除用戶"}
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
  );
}
