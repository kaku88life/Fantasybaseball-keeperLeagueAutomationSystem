"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getKeeperOptions,
  getKeeperSelections,
  getTeamRoster,
  submitKeeperList,
  updateKeeperSelections,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ContractBadge from "@/components/ContractBadge";
import {
  getActionLabel,
  validateSelections,
  type Selection,
} from "@/lib/validation";
import type {
  ContractType,
  PlayerKeeperOptions,
  Team,
  ValidationResult,
} from "@/types";

export default function KeeperSelectionPage() {
  const params = useParams();
  const year = Number(params.year);
  const teamId = Number(params.teamId);
  const { user } = useAuth();

  const [team, setTeam] = useState<Team | null>(null);
  const [options, setOptions] = useState<PlayerKeeperOptions[]>([]);
  const [selections, setSelections] = useState<Record<string, Selection>>({});
  const [serverValidation, setServerValidation] =
    useState<ValidationResult | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");

  const isOwnTeam = user?.team_id === teamId;
  const canEdit = !!(isOwnTeam || user?.is_commissioner) && !isSubmitted;

  // Auto-save timer ref
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectionsRef = useRef(selections);
  selectionsRef.current = selections;

  // Client-side validation (instant)
  const clientValidation = useMemo(() => {
    if (!team) return null;
    return validateSelections(team, selections);
  }, [team, selections]);

  // Use client validation for display
  const displayValidation = clientValidation;
  const fin = displayValidation?.financial_summary;

  // Load data
  useEffect(() => {
    if (!year || !teamId) return;
    setError("");

    Promise.all([getTeamRoster(teamId, year), getKeeperOptions(teamId, year)])
      .then(([t, o]) => {
        setTeam(t);
        setOptions(o);
      })
      .catch((e) => setError(e.message));
  }, [year, teamId]);

  // Load saved selections
  useEffect(() => {
    if (!year || !teamId || !user) return;

    getKeeperSelections(teamId, year)
      .then((data) => {
        const sel: Record<string, Selection> = {};
        for (const s of data.selections) {
          sel[s.player_name] = {
            action: s.action,
            extension_years: s.extension_years,
          };
        }
        setSelections(sel);
        setServerValidation(data.validation);
        setIsSubmitted(data.is_submitted);
      })
      .catch(() => {
        // No saved selections yet
      });
  }, [year, teamId, user]);

  // Auto-save function
  const autoSave = useCallback(async () => {
    const currentSel = selectionsRef.current;
    const entries = Object.entries(currentSel);
    if (entries.length === 0) return;

    setSaveStatus("saving");
    try {
      const sels = entries.map(([name, s]) => ({
        player_name: name,
        action: s.action,
        extension_years: s.extension_years,
      }));
      const result = await updateKeeperSelections(teamId, year, sels);
      setServerValidation(result.validation);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      setSaveStatus("error");
    }
  }, [teamId, year]);

  // Update a single player's selection (with debounced auto-save)
  const updateSelection = useCallback(
    (playerName: string, action: string, extensionYears: number = 0) => {
      setSelections((prev) => ({
        ...prev,
        [playerName]: { action, extension_years: extensionYears },
      }));

      // Debounced auto-save (1.5s after last change)
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(autoSave, 1500);
    },
    [autoSave],
  );

  // Manual save
  const handleSave = useCallback(async () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setSaving(true);
    try {
      const sels = Object.entries(selections).map(([name, s]) => ({
        player_name: name,
        action: s.action,
        extension_years: s.extension_years,
      }));
      const result = await updateKeeperSelections(teamId, year, sels);
      setServerValidation(result.validation);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [selections, teamId, year]);

  // Submit keeper list
  const handleSubmit = useCallback(async () => {
    if (
      !confirm(
        "確定要繳交留用名單嗎？繳交後將鎖定你的選擇，無法再修改。",
      )
    ) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const sels = Object.entries(selections).map(([name, s]) => ({
        player_name: name,
        action: s.action,
        extension_years: s.extension_years,
      }));
      await updateKeeperSelections(teamId, year, sels);
      await submitKeeperList(teamId, year);
      setIsSubmitted(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }, [selections, teamId, year]);

  // Compute next contract display for each player based on current selection
  const getNextContract = useCallback(
    (playerName: string): string | null => {
      const sel = selections[playerName];
      if (!sel) return null;

      const playerOpts = options.find((o) => o.player.name === playerName);
      if (!playerOpts) return null;

      for (const opt of playerOpts.options) {
        if (
          opt.keep_action === sel.action &&
          opt.extension_years === sel.extension_years
        ) {
          return opt.next_contract;
        }
      }
      return null;
    },
    [selections, options],
  );

  if (error && !team) {
    return (
      <div className="py-10 text-center">
        <p className="text-red-600">{error}</p>
        <Link
          href={`/${year}`}
          className="mt-4 inline-block text-sm text-indigo-600 hover:underline"
        >
          返回聯盟總覽 Back to Overview
        </Link>
      </div>
    );
  }

  if (!team) {
    return <div className="py-10 text-center text-gray-500">Loading...</div>;
  }

  // Separate players by type for display
  const activePlayers = team.players.filter(
    (p) => p.contract.contract_type !== "R",
  );
  const benchPlayers = team.players.filter(
    (p) => p.contract.contract_type === "R",
  );

  return (
    <div className="pb-10">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Link
              href={`/${year}`}
              className="text-gray-400 hover:text-gray-600"
            >
              &larr;
            </Link>
            <h1 className="text-2xl font-bold">
              {team.manager_name} - {year} 留用名單
            </h1>
          </div>
          {team.team_name && (
            <p className="ml-8 text-sm text-gray-500">{team.team_name}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {isSubmitted && (
            <span className="rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">
              已繳交 Submitted
            </span>
          )}
          {saveStatus === "saving" && (
            <span className="text-xs text-gray-400">儲存中...</span>
          )}
          {saveStatus === "saved" && (
            <span className="text-xs text-green-500">已儲存</span>
          )}
          {saveStatus === "error" && (
            <span className="text-xs text-red-500">儲存失敗</span>
          )}
        </div>
      </div>

      {/* Financial Summary */}
      {fin && (
        <div className="mb-6 rounded-lg border bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">
            財務摘要 <span className="font-normal text-gray-400">Financial Summary</span>
          </h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
            <div className="rounded bg-gray-50 p-3">
              <p className="text-xs text-gray-500">薪資上限 Salary Cap</p>
              <p className="text-lg font-bold">${fin.salary_cap}</p>
            </div>
            {fin.ranking_bonus > 0 && (
              <div className="rounded bg-yellow-50 p-3">
                <p className="text-xs text-gray-500">排名獎勵 Ranking Bonus</p>
                <p className="text-lg font-bold text-yellow-600">
                  +${fin.ranking_bonus}
                </p>
              </div>
            )}
            {fin.trade_compensation !== 0 && (
              <div className={`rounded p-3 ${fin.trade_compensation > 0 ? "bg-purple-50" : "bg-orange-50"}`}>
                <p className="text-xs text-gray-500">交易補償 Trade Comp.</p>
                <p className={`text-lg font-bold ${fin.trade_compensation > 0 ? "text-purple-600" : "text-orange-600"}`}>
                  {fin.trade_compensation > 0 ? "+" : ""}${fin.trade_compensation}
                </p>
              </div>
            )}
            <div className="rounded bg-gray-50 p-3">
              <p className="text-xs text-gray-500">留用成本 Keeper Cost</p>
              <p className="text-lg font-bold">${fin.keeper_cost}</p>
            </div>
            {fin.buyout_salary_cost > 0 && (
              <div className="rounded bg-red-50 p-3">
                <p className="text-xs text-gray-500">買斷成本 Buyout Cost</p>
                <p className="text-lg font-bold text-red-600">
                  -${fin.buyout_salary_cost}
                </p>
              </div>
            )}
            <div
              className={`rounded p-3 ${
                fin.available_salary < 0
                  ? "bg-red-100"
                  : fin.available_salary < 20
                    ? "bg-yellow-50"
                    : "bg-green-50"
              }`}
            >
              <p className="text-xs text-gray-500">可用薪資 Cap Space</p>
              <p
                className={`text-lg font-bold ${
                  fin.available_salary < 0
                    ? "text-red-600"
                    : fin.available_salary < 20
                      ? "text-yellow-600"
                      : "text-green-600"
                }`}
              >
                ${fin.available_salary}
              </p>
            </div>
            <div className="rounded bg-gray-50 p-3">
              <p className="text-xs text-gray-500">FAAB 預算 Budget</p>
              <p className="text-lg font-bold">${fin.faab_budget}</p>
            </div>
            {fin.faab_adjustment !== 0 && (
              <div className={`rounded p-3 ${fin.faab_adjustment > 0 ? "bg-purple-50" : "bg-orange-50"}`}>
                <p className="text-xs text-gray-500">FAAB 調整 Adjustment</p>
                <p className={`text-lg font-bold ${fin.faab_adjustment > 0 ? "text-purple-600" : "text-orange-600"}`}>
                  {fin.faab_adjustment > 0 ? "+" : ""}${fin.faab_adjustment}
                </p>
              </div>
            )}
            {fin.buyout_faab_cost > 0 && (
              <div className="rounded bg-red-50 p-3">
                <p className="text-xs text-gray-500">FAAB 買斷 Buyout</p>
                <p className="text-lg font-bold text-red-600">
                  -${fin.buyout_faab_cost}
                </p>
              </div>
            )}
            <div className="rounded bg-blue-50 p-3">
              <p className="text-xs text-gray-500">活躍留用 Active Keepers</p>
              <p className="text-lg font-bold">
                {fin.active_keeper_count}
                <span className="text-sm font-normal text-gray-400">
                  /6~10
                </span>
              </p>
            </div>
            <div className="rounded bg-gray-50 p-3">
              <p className="text-xs text-gray-500">板凳新秀 Bench Rookie (R)</p>
              <p className="text-lg font-bold">
                {fin.bench_keeper_count}
                <span className="text-sm font-normal text-gray-400">/2</span>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Validation Messages */}
      {displayValidation && (
        <div className="mb-4 space-y-2">
          {displayValidation.errors.map((e, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              <span className="mt-0.5 shrink-0">&#x26A0;</span>
              <span>{e}</span>
            </div>
          ))}
          {displayValidation.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-700"
            >
              <span className="mt-0.5 shrink-0">&#x26A0;</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Active Players Table */}
      <div className="mb-2 text-sm font-semibold text-gray-600">
        活躍球員 Active Players ({activePlayers.length})
      </div>
      <PlayerTable
        players={activePlayers}
        options={options}
        selections={selections}
        canEdit={canEdit}
        getNextContract={getNextContract}
        updateSelection={updateSelection}
      />

      {/* Bench Players (R contracts) */}
      {benchPlayers.length > 0 && (
        <>
          <div className="mb-2 mt-6 text-sm font-semibold text-gray-600">
            板凳新秀 Bench Rookie / R 約 ({benchPlayers.length})
          </div>
          <PlayerTable
            players={benchPlayers}
            options={options}
            selections={selections}
            canEdit={canEdit}
            getNextContract={getNextContract}
            updateSelection={updateSelection}
          />
        </>
      )}

      {/* Buyout Records */}
      {team.buyout_records.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-gray-600">
            買斷紀錄 Buyout Records
          </h3>
          <div className="overflow-x-auto rounded-lg border bg-white">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left">球員 Player</th>
                  <th className="px-3 py-2 text-left">原合約 Contract</th>
                  <th className="px-3 py-2 text-right">薪資成本 Salary</th>
                  <th className="px-3 py-2 text-right">FAAB 成本</th>
                </tr>
              </thead>
              <tbody>
                {team.buyout_records.map((b) => (
                  <tr key={b.player_name} className="border-b">
                    <td className="px-3 py-2">{b.player_name}</td>
                    <td className="px-3 py-2">{b.original_contract}</td>
                    <td className="px-3 py-2 text-right">
                      ${b.buyout_salary_cost}
                    </td>
                    <td className="px-3 py-2 text-right">
                      ${b.buyout_faab_cost}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Action buttons */}
      {canEdit && (
        <div className="mt-6 flex items-center gap-4">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-gray-700 px-4 py-2 text-sm text-white hover:bg-gray-600 disabled:opacity-50"
          >
            {saving ? "儲存中..." : "手動儲存 Save"}
          </button>
          <button
            onClick={handleSubmit}
            disabled={
              submitting ||
              !displayValidation?.is_valid ||
              Object.keys(selections).length === 0
            }
            className="rounded bg-green-600 px-5 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
          >
            {submitting ? "繳交中..." : "繳交留用名單 Submit"}
          </button>
          <span className="text-xs text-gray-400">
            選擇變更後會自動儲存 Auto-save enabled
          </span>
        </div>
      )}
    </div>
  );
}

// ---- Sub-components ----

function PlayerTable({
  players,
  options,
  selections,
  canEdit,
  getNextContract,
  updateSelection,
}: {
  players: import("@/types").Player[];
  options: PlayerKeeperOptions[];
  selections: Record<string, Selection>;
  canEdit: boolean;
  getNextContract: (name: string) => string | null;
  updateSelection: (name: string, action: string, ext: number) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="w-full text-sm">
        <thead className="border-b bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
              守備 Pos.
            </th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
              球員 Player
            </th>
            <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
              薪資 Salary
            </th>
            <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
              合約 Contract
            </th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
              動作 Action
            </th>
            <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
              下季合約 Next
            </th>
          </tr>
        </thead>
        <tbody>
          {players.map((player) => {
            const playerOpts = options.find(
              (o) => o.player.name === player.name,
            );
            const sel = selections[player.name];
            const nextContract = getNextContract(player.name);
            const ct = player.contract.contract_type as ContractType;

            const isReleased = sel?.action === "release";
            const isFA = ct === "O";

            return (
              <tr
                key={player.name}
                className={`border-b transition-colors ${
                  isReleased
                    ? "bg-red-50/50 text-gray-400"
                    : isFA
                      ? "bg-gray-50 text-gray-400"
                      : "hover:bg-gray-50"
                }`}
              >
                <td className="px-3 py-2">
                  <span className="text-xs">{player.position}</span>
                </td>
                <td className="px-3 py-2 font-medium">{player.name}</td>
                <td className="px-3 py-2 text-right">
                  ${player.contract.salary}
                </td>
                <td className="px-3 py-2 text-center">
                  <ContractBadge
                    type={ct}
                    display={player.contract.display}
                  />
                </td>
                <td className="px-3 py-2">
                  {canEdit && playerOpts ? (
                    <select
                      value={
                        sel ? `${sel.action}:${sel.extension_years}` : ""
                      }
                      onChange={(e) => {
                        const [action, ext] = e.target.value.split(":");
                        updateSelection(
                          player.name,
                          action,
                          Number(ext) || 0,
                        );
                      }}
                      className={`w-full max-w-[260px] rounded border px-2 py-1 text-sm ${
                        !sel
                          ? "border-yellow-300 bg-yellow-50"
                          : "border-gray-300"
                      }`}
                    >
                      <option value="">-- 請選擇 --</option>
                      {playerOpts.options.map((opt, i) => (
                        <option
                          key={i}
                          value={`${opt.keep_action}:${opt.extension_years}`}
                        >
                          {getActionLabel(
                            ct,
                            opt.keep_action,
                            opt.extension_years,
                            player.contract.salary,
                          )}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-gray-500">
                      {sel
                        ? getActionLabel(
                            ct,
                            sel.action,
                            sel.extension_years,
                            player.contract.salary,
                          )
                        : isFA
                          ? "自由球員"
                          : "--"}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-center">
                  {nextContract ? (
                    nextContract === "FA" ? (
                      <span className="text-xs text-gray-400">FA</span>
                    ) : (
                      <ContractBadge
                        type={
                          nextContract.includes("/N")
                            ? "N"
                            : nextContract.includes("/O")
                              ? "O"
                              : nextContract.includes("/B")
                                ? "B"
                                : nextContract.includes("/A")
                                  ? "A"
                                  : nextContract.includes("/R")
                                    ? "R"
                                    : "FA"
                        }
                        display={nextContract}
                      />
                    )
                  ) : (
                    <span className="text-gray-300">--</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
