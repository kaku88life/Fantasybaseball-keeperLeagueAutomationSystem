"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getUsers, getTeams, assignTeam, setCommissioner } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UserWithTeam, DBTeam } from "@/types";

export default function UserManagementPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<UserWithTeam[]>([]);
  const [teams, setTeams] = useState<DBTeam[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

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
                <th className="px-4 py-3">Yahoo 暱稱 Nickname</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">對應隊伍 Team</th>
                <th className="px-4 py-3">最後登入 Last Login</th>
                <th className="px-4 py-3">Commissioner</th>
                <th className="px-4 py-3">操作 Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{u.yahoo_nickname || "-"}</td>
                  <td className="px-4 py-3 text-gray-500">{u.yahoo_email || "-"}</td>
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
