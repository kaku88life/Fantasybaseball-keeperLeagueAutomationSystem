"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import {
  getKeeperPageData,
  getTeamRoster,
  submitKeeperList,
  updateKeeperSelections,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ContractBadge from "@/components/ContractBadge";
import LoadingSpinner from "@/components/LoadingSpinner";
import PlayerStatsModal from "@/components/PlayerStatsModal";
import PositionFilter from "@/components/PositionFilter";
import {
  computeBuyoutCost,
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

// ========== Read-only Roster View (for in-season tab) ==========

function RosterView({ year, teamId }: { year: number; teamId: number }) {
  const { data: roster, error, isLoading } = useSWR(
    year && teamId ? `roster-${teamId}-${year + 1}` : null,
    () => getTeamRoster(teamId, year + 1),
  );
  const [statsPlayer, setStatsPlayer] = useState<{ name: string; position: string } | null>(null);

  if (isLoading) return <LoadingSpinner />;
  if (error) return <div className="py-10 text-center text-red-500">Failed to load roster</div>;
  if (!roster) return null;

  // Group players by position category
  const active = roster.players.filter(
    (p) => p.contract.contract_type !== "R",
  );
  const farm = roster.players.filter(
    (p) => p.contract.contract_type === "R",
  );

  // MLB team concentration
  const teamCounts: Record<string, number> = {};
  for (const p of roster.players) {
    const t = p.mlb_team || "???";
    teamCounts[t] = (teamCounts[t] || 0) + 1;
  }
  const sortedTeams = Object.entries(teamCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  return (
    <div className="pb-10">
      <div className="mb-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <Link href={`/${year}`} className="text-gray-400 hover:text-gray-600">&larr;</Link>
          <h1 className="text-xl font-bold sm:text-2xl">
            {roster.manager_name} - {year} 賽季中名單
          </h1>
        </div>
        {roster.team_name && (
          <p className="mt-1 pl-6 text-sm text-gray-500 sm:pl-8">{roster.team_name}</p>
        )}
      </div>

      {/* MLB Team Distribution */}
      <div className="mb-4 rounded-lg border bg-white p-3 sm:p-4">
        <h3 className="mb-2 text-xs font-semibold text-gray-500 uppercase">MLB 球隊分布</h3>
        <div className="flex flex-wrap gap-1.5">
          {sortedTeams.map(([team, count]) => (
            <span
              key={team}
              className={`rounded px-2 py-0.5 text-xs font-bold ${
                count >= 5 ? "bg-green-200 text-green-800" :
                count >= 3 ? "bg-amber-200 text-amber-800" :
                "bg-gray-200 text-gray-600"
              }`}
            >
              {team} {count}
            </span>
          ))}
        </div>
        <p className="mt-1 text-[10px] text-gray-400">
          共 {roster.players.length} 名球員（Active {active.length} + Farm {farm.length}）
        </p>
      </div>

      {/* Active Players */}
      <h3 className="mb-2 text-sm font-semibold text-gray-700">
        Active Roster ({active.length})
      </h3>
      <div className="mb-6 overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-gray-400 sm:px-3">球員</th>
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3">位置</th>
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3">MLB</th>
              <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-gray-400 sm:px-3">合約</th>
              <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-gray-400 sm:px-3">薪資</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {active.map((p) => (
              <tr
                key={p.name}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => setStatsPlayer({ name: p.name, position: p.position })}
              >
                <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3">
                  {p.name}
                </td>
                <td className="px-2 py-1.5 text-center text-gray-500 sm:px-3">{p.position}</td>
                <td className="px-2 py-1.5 text-center sm:px-3">
                  <span className="text-gray-600">{p.mlb_team || "—"}</span>
                </td>
                <td className="px-2 py-1.5 text-center sm:px-3">
                  <ContractBadge type={p.contract.contract_type as ContractType} display={p.contract.display || `$${p.contract.salary}/${p.contract.contract_type}`} />
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 text-right font-bold tabular-nums text-indigo-700 sm:px-3">
                  ${p.contract.salary}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Farm Rookies */}
      {farm.length > 0 && (
        <>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">
            Farm Rookies ({farm.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-xs sm:text-sm">
              <thead className="bg-purple-50">
                <tr>
                  <th className="px-2 py-1.5 text-left text-[10px] font-medium uppercase text-purple-400 sm:px-3">球員</th>
                  <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-purple-400 sm:px-3">位置</th>
                  <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-purple-400 sm:px-3">MLB</th>
                  <th className="px-2 py-1.5 text-center text-[10px] font-medium uppercase text-purple-400 sm:px-3">合約</th>
                  <th className="px-2 py-1.5 text-right text-[10px] font-medium uppercase text-purple-400 sm:px-3">薪資</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {farm.map((p) => (
                  <tr
                    key={p.name}
                    className="hover:bg-purple-50 cursor-pointer"
                    onClick={() => setStatsPlayer({ name: p.name, position: p.position })}
                  >
                    <td className="whitespace-nowrap px-2 py-1.5 font-medium text-gray-900 sm:px-3">
                      {p.name}
                    </td>
                    <td className="px-2 py-1.5 text-center text-gray-500 sm:px-3">{p.position}</td>
                    <td className="px-2 py-1.5 text-center text-gray-600 sm:px-3">{p.mlb_team || "—"}</td>
                    <td className="px-2 py-1.5 text-center sm:px-3">
                      <ContractBadge type="R" display={`$${p.contract.salary}/R`} />
                    </td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right font-bold tabular-nums text-indigo-700 sm:px-3">
                      ${p.contract.salary}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {statsPlayer && (
        <PlayerStatsModal
          playerName={statsPlayer.name}
          position={statsPlayer.position}
          onClose={() => setStatsPlayer(null)}
        />
      )}
    </div>
  );
}

// ========== Main Page ==========

export default function KeeperSelectionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const year = Number(params.year);
  const teamId = Number(params.teamId);
  const { user } = useAuth();

  // If ?view=roster, show read-only roster view (from in-season tab)
  if (searchParams.get("view") === "roster") {
    return <RosterView year={year} teamId={teamId} />;
  }

  // SWR: single combined API call (roster + options + selections)
  // Track which year+team combo was last initialized to reset on navigation
  const [loadedKey, setLoadedKey] = useState("");
  const currentKey = `${teamId}-${year}`;
  const { data: pageData, error: pageErr, mutate: retryLoad } = useSWR(
    year && teamId ? `keeper-page-${teamId}-${year}` : null,
    () => getKeeperPageData(teamId, year),
    {
      onSuccess: (data) => {
        // Initialize selections from server on first load or when year/team changes
        if (loadedKey !== currentKey) {
          const sel: Record<string, Selection> = {};
          for (const s of data.selections.selections) {
            sel[s.player_name] = {
              action: s.action,
              extension_years: s.extension_years,
            };
          }
          setSelections(sel);
          setServerValidation(data.selections.validation);
          setLocalSubmitted(false);
          setLoadedKey(currentKey);
        }
      },
    },
  );
  const team = pageData?.roster ?? null;
  const options = pageData?.options ?? [];
  const [actionError, setActionError] = useState("");
  const error = pageErr?.message || actionError;

  const [selections, setSelections] = useState<Record<string, Selection>>({});
  const [serverValidation, setServerValidation] =
    useState<ValidationResult | null>(null);
  // Derive isSubmitted from server data directly; localSubmitted is for optimistic UI after submit
  const [localSubmitted, setLocalSubmitted] = useState(false);
  const isSubmitted = localSubmitted || (pageData?.selections?.is_submitted ?? false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [saveStatus, setSaveStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [statsPlayer, setStatsPlayer] = useState<{
    name: string;
    position: string;
  } | null>(null);
  const [positionFilter, setPositionFilter] = useState<string>("ALL");

  // Reset local state when year/team changes (e.g. client-side navigation between years)
  useEffect(() => {
    setLocalSubmitted(false);
    setSelections({});
    setServerValidation(null);
    setSaveStatus("idle");
    setActionError("");
  }, [year, teamId]);

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
      setActionError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [selections, teamId, year]);

  // Submit keeper list
  const handleSubmit = useCallback(async () => {
    if (!team) return;

    // Auto-fill unselected players: O -> fa, others -> release
    const autoFilled = { ...selections };
    const unselectedNames: string[] = [];
    for (const player of team.players) {
      if (!autoFilled[player.name]) {
        const ct = player.contract.contract_type;
        const defaultAction = ct === "O" ? "fa" : "release";
        autoFilled[player.name] = { action: defaultAction, extension_years: 0 };
        unselectedNames.push(`${player.name} (${player.contract.display} -> ${defaultAction === "fa" ? "FA" : "Release"})`);
      }
    }

    // Show confirmation with auto-fill info
    const autoFillMsg = unselectedNames.length > 0
      ? `\n\n以下 ${unselectedNames.length} 位球員未選擇，將自動判定：\n${unselectedNames.join("\n")}`
      : "";

    if (
      !confirm(
        `確定要繳交留用名單嗎？繳交後將鎖定你的選擇，無法再修改。${autoFillMsg}`,
      )
    ) {
      return;
    }

    // Update state with auto-filled selections
    if (unselectedNames.length > 0) {
      setSelections(autoFilled);
    }

    setSubmitting(true);
    setActionError("");
    try {
      const sels = Object.entries(autoFilled).map(([name, s]) => ({
        player_name: name,
        action: s.action,
        extension_years: s.extension_years,
      }));
      await updateKeeperSelections(teamId, year, sels);
      await submitKeeperList(teamId, year);
      setLocalSubmitted(true);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }, [selections, team, teamId, year]);

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
      // release_normal uses same next_contract as release (both -> FA)
      if (sel.action === "release_normal") {
        for (const opt of playerOpts.options) {
          if (opt.keep_action === "release") {
            return opt.next_contract;
          }
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
        <div className="mt-4 flex flex-col items-center gap-3">
          <button
            onClick={() => retryLoad()}
            className="rounded bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500"
          >
            重試 Retry
          </button>
          <Link
            href={`/${year}`}
            className="text-sm text-indigo-600 hover:underline"
          >
            返回聯盟總覽 Back to Overview
          </Link>
        </div>
      </div>
    );
  }

  if (!team) {
    return <LoadingSpinner message="載入球員資料中..." />;
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
      <div className="mb-4">
        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            href={`/${year}`}
            className="text-gray-400 hover:text-gray-600"
          >
            &larr;
          </Link>
          <h1 className="text-xl font-bold sm:text-2xl">
            {team.manager_name} - {year} 留用名單
          </h1>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 pl-6 sm:pl-8">
          {team.team_name && (
            <p className="text-sm text-gray-500">{team.team_name}</p>
          )}
          {isSubmitted && (
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 sm:px-3 sm:py-1 sm:text-sm">
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
              <p className="text-base font-bold sm:text-lg">${fin.salary_cap}</p>
            </div>
            {fin.ranking_bonus > 0 && (
              <div className="rounded bg-yellow-50 p-3">
                <p className="text-xs text-gray-500">排名獎勵 Ranking Bonus</p>
                <p className="text-base font-bold sm:text-lg text-yellow-600">
                  +${fin.ranking_bonus}
                </p>
              </div>
            )}
            {fin.trade_compensation !== 0 && (
              <div className={`rounded p-3 ${fin.trade_compensation > 0 ? "bg-purple-50" : "bg-orange-50"}`}>
                <p className="text-xs text-gray-500">交易補償 Trade Comp.</p>
                <p className={`text-base font-bold sm:text-lg ${fin.trade_compensation > 0 ? "text-purple-600" : "text-orange-600"}`}>
                  {fin.trade_compensation > 0 ? "+" : ""}${fin.trade_compensation}
                </p>
              </div>
            )}
            <div className="rounded bg-gray-50 p-3">
              <p className="text-xs text-gray-500">留用成本 Keeper Cost</p>
              <p className="text-base font-bold sm:text-lg">${fin.keeper_cost}</p>
            </div>
            {fin.buyout_salary_cost > 0 && (
              <div className="rounded bg-red-50 p-3">
                <p className="text-xs text-gray-500">買斷成本 Buyout Cost</p>
                <p className="text-base font-bold sm:text-lg text-red-600">
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
                className={`text-base font-bold sm:text-lg ${
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
              <p className="text-base font-bold sm:text-lg">${fin.faab_budget}</p>
            </div>
            {fin.faab_adjustment !== 0 && (
              <div className={`rounded p-3 ${fin.faab_adjustment > 0 ? "bg-purple-50" : "bg-orange-50"}`}>
                <p className="text-xs text-gray-500">FAAB 調整 Adjustment</p>
                <p className={`text-base font-bold sm:text-lg ${fin.faab_adjustment > 0 ? "text-purple-600" : "text-orange-600"}`}>
                  {fin.faab_adjustment > 0 ? "+" : ""}${fin.faab_adjustment}
                </p>
              </div>
            )}
            {fin.buyout_faab_cost > 0 && (
              <div className="rounded bg-red-50 p-3">
                <p className="text-xs text-gray-500">FAAB 買斷 Buyout</p>
                <p className="text-base font-bold sm:text-lg text-red-600">
                  -${fin.buyout_faab_cost}
                </p>
              </div>
            )}
            <div className="rounded bg-blue-50 p-3">
              <p className="text-xs text-gray-500">目前已留用球員名單 Active Keepers</p>
              <p className="text-base font-bold sm:text-lg">
                {fin.active_keeper_count}
                <span className="text-sm font-normal text-gray-400">
                  /12~15
                </span>
              </p>
            </div>
            <div className="rounded bg-gray-50 p-3">
              <p className="text-xs text-gray-500">農場新秀名單 Rookie (R)</p>
              <p className="text-base font-bold sm:text-lg">
                {fin.farm_rookie_count}
                <span className="text-sm font-normal text-gray-400">/2</span>
              </p>
            </div>
          </div>

          {/* Team Concentration (kept players only) */}
          {(() => {
            const keptTeamCounts: Record<string, number> = {};
            for (const p of team.players) {
              if (!p.mlb_team) continue;
              const sel = selections[p.name];
              const ct = p.contract.contract_type;
              // Count kept players: has keep/extend/rookie action, or mandatory N contract
              const isKept = sel
                ? !["release", "release_normal", "fa"].includes(sel.action)
                : ct === "N"; // N contracts are mandatory keepers if no selection
              if (!isKept) continue;
              if (ct === "O") continue; // O contracts become FA
              keptTeamCounts[p.mlb_team] = (keptTeamCounts[p.mlb_team] || 0) + 1;
            }
            const concentrated = Object.entries(keptTeamCounts)
              .filter(([, c]) => c >= 2)
              .sort((a, b) => b[1] - a[1]);
            if (concentrated.length === 0) return null;
            return (
              <div className="mt-3 rounded bg-sky-50 p-3">
                <p className="text-xs text-gray-500">同隊球員集中度 Team Concentration (留用)</p>
                <div className="mt-1 flex flex-wrap gap-2">
                  {concentrated.map(([t, c]) => (
                    <span
                      key={t}
                      className={`rounded px-2 py-0.5 text-xs font-bold ${
                        c >= 3
                          ? "bg-amber-200 text-amber-800"
                          : "bg-sky-100 text-sky-700"
                      }`}
                    >
                      {t}: {c}
                    </span>
                  ))}
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Validation Messages */}
      {displayValidation && (
        <div className="mb-4 space-y-2">
          {displayValidation.errors.map((e, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 sm:text-sm"
            >
              <span className="mt-0.5 shrink-0">&#x26A0;</span>
              <span>{e}</span>
            </div>
          ))}
          {displayValidation.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded border border-yellow-200 bg-yellow-50 px-3 py-2 text-xs text-yellow-700 sm:text-sm"
            >
              <span className="mt-0.5 shrink-0">&#x26A0;</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {isSubmitted ? (
        /* Submitted: unified sorted view (O/N/B/A/R/Buyout/Release) */
        <>
          <div className="mb-2 text-sm font-semibold text-gray-600">
            留用名單總覽 Keeper Summary ({team.players.length})
          </div>
          <PlayerTable
            players={team.players}
            options={options}
            selections={selections}
            canEdit={false}
            isSubmitted
            getNextContract={getNextContract}
            updateSelection={updateSelection}
            onPlayerClick={(name, pos) => setStatsPlayer({ name, position: pos })}
            mandatoryKeepers={new Set(options.filter(o => o.is_mandatory_keeper).map(o => o.player.name))}
          />
        </>
      ) : (
        <>
          {/* Active Players Table */}
          <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
            <span className="text-sm font-semibold text-gray-600">
              球員名單 Active ({activePlayers.length})
            </span>
            <PositionFilter
              items={activePlayers}
              value={positionFilter}
              onChange={setPositionFilter}
            />
            <TeamConcentrationBadges players={activePlayers} />
          </div>
          <PlayerTable
            players={activePlayers}
            options={options}
            selections={selections}
            canEdit={canEdit}
            getNextContract={getNextContract}
            updateSelection={updateSelection}
            onPlayerClick={(name, pos) => setStatsPlayer({ name, position: pos })}
            positionFilter={positionFilter}
            mandatoryKeepers={new Set(options.filter(o => o.is_mandatory_keeper).map(o => o.player.name))}
          />

          {/* Bench Players (R contracts) */}
          {benchPlayers.length > 0 && (
            <>
              <div className="mb-2 mt-6 text-sm font-semibold text-gray-600">
                農場新秀名單 Rookie / R 約 ({benchPlayers.length})
              </div>
              <PlayerTable
                players={benchPlayers}
                options={options}
                selections={selections}
                canEdit={canEdit}
                getNextContract={getNextContract}
                updateSelection={updateSelection}
                onPlayerClick={(name, pos) => setStatsPlayer({ name, position: pos })}
                mandatoryKeepers={new Set(options.filter(o => o.is_mandatory_keeper).map(o => o.player.name))}
              />
            </>
          )}
        </>
      )}

      {/* Buyout Records */}
      {team.buyout_records.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-gray-600">
            買斷紀錄 Buyout Records ({team.buyout_records.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border bg-white">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">球員 Player</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">原合約 Contract</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">薪資成本 Salary</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">FAAB 成本</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">備註 Note</th>
                </tr>
              </thead>
              <tbody>
                {team.buyout_records.map((b) => {
                  const isLegalIssue = b.buyout_salary_cost === 0 && b.buyout_faab_cost === 0;
                  return (
                    <tr key={b.player_name} className={`border-b ${isLegalIssue ? "bg-gray-50 text-gray-400" : ""}`}>
                      <td className="px-3 py-2">{b.player_name}</td>
                      <td className="px-3 py-2">{b.original_contract}</td>
                      <td className="px-3 py-2 text-right">
                        {isLegalIssue ? (
                          <span className="text-gray-400">--</span>
                        ) : (
                          <span className="text-red-600">${b.buyout_salary_cost}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {isLegalIssue ? (
                          <span className="text-gray-400">--</span>
                        ) : b.buyout_faab_cost > 0 ? (
                          <span className="text-red-600">${b.buyout_faab_cost}</span>
                        ) : (
                          <span className="text-gray-400">$0</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500">
                        {b.note || (isLegalIssue ? "Legal Issue (no cost)" : b.use_faab ? "FAAB buyout" : "")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot className="border-t bg-gray-50 font-medium">
                <tr>
                  <td className="px-3 py-2" colSpan={2}>
                    合計 Total
                  </td>
                  <td className="px-3 py-2 text-right text-red-600">
                    ${team.buyout_records.reduce((sum, b) => sum + b.buyout_salary_cost, 0)}
                  </td>
                  <td className="px-3 py-2 text-right text-red-600">
                    ${team.buyout_records.reduce((sum, b) => sum + b.buyout_faab_cost, 0)}
                  </td>
                  <td className="px-3 py-2"></td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="mt-1.5 text-xs text-gray-400">
            買斷薪資從 Salary Cap 扣除，FAAB 買斷從 FAAB 預算扣除。Legal Issue 球員不計成本。
          </p>
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
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="min-h-[44px] rounded bg-gray-700 px-4 py-2 text-sm text-white hover:bg-gray-600 disabled:opacity-50"
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
              className="min-h-[44px] rounded bg-green-600 px-5 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50"
            >
              {submitting ? "繳交中..." : "繳交留用名單 Submit"}
            </button>
          </div>
          <span className="text-xs text-gray-400">
            選擇變更後會自動儲存 Auto-save enabled
          </span>
        </div>
      )}

      {/* Player Stats Modal */}
      {statsPlayer && (
        <PlayerStatsModal
          playerName={statsPlayer.name}
          position={statsPlayer.position}
          onClose={() => setStatsPlayer(null)}
        />
      )}
    </div>
  );
}

// ---- Helper: contract sort order for submitted view ----
// Priority: O(1) → N(2) → B(3) → A(4) → R(5) → Buyout(6) → Release/FA(7)
function getContractSortOrder(
  nextContract: string | null,
  action: string | undefined,
  currentContractType: string,
): number {
  if (currentContractType === "O") return 7;
  if (action === "release" || action === "release_normal") {
    return currentContractType === "N" ? 6 : 7;
  }
  if (nextContract?.includes("/O")) return 1;
  if (nextContract?.includes("/N")) return 2;
  if (nextContract?.includes("/B")) return 3;
  if (nextContract?.includes("/A")) return 4;
  if (nextContract?.includes("/R")) return 5;
  if (nextContract === "FA") return 7;
  return 8;
}

const CONTRACT_GROUP_CONFIG: Record<number, { label: string; style: string }> = {
  1: { label: "O 約 — 到期年 Final Year", style: "bg-gray-200 text-gray-700" },
  2: { label: "N 約 — 延長 Extension", style: "bg-blue-100 text-blue-800" },
  3: { label: "B 約 — 第二年 2nd Year", style: "bg-green-100 text-green-800" },
  4: { label: "A 約 — 第一年 1st Year", style: "bg-indigo-100 text-indigo-800" },
  5: { label: "R 約 — 農場新秀 Rookie", style: "bg-purple-100 text-purple-800" },
  6: { label: "買斷 Buyout", style: "bg-amber-100 text-amber-800" },
  7: { label: "不保留 Release / FA", style: "bg-red-100 text-red-800" },
  8: { label: "其他 Other", style: "bg-gray-100 text-gray-600" },
};

// ---- Sub-components ----

function PlayerTable({
  players,
  options,
  selections,
  canEdit,
  isSubmitted = false,
  getNextContract,
  updateSelection,
  onPlayerClick,
  positionFilter = "ALL",
  mandatoryKeepers = new Set(),
}: {
  players: import("@/types").Player[];
  options: PlayerKeeperOptions[];
  selections: Record<string, Selection>;
  canEdit: boolean;
  isSubmitted?: boolean;
  getNextContract: (name: string) => string | null;
  updateSelection: (name: string, action: string, ext: number) => void;
  onPlayerClick: (name: string, position: string) => void;
  positionFilter?: string;
  mandatoryKeepers?: Set<string>;
}) {
  const filteredPlayers = useMemo(() => {
    if (positionFilter === "ALL") return players;
    return players.filter((p) => {
      const positions = p.position.split(",").map((s) => s.trim());
      if (positionFilter === "IF") {
        return positions.some((pos) =>
          ["C", "1B", "2B", "3B", "SS"].includes(pos),
        );
      }
      if (positionFilter === "OF") {
        return positions.some((pos) =>
          ["LF", "CF", "RF", "OF"].includes(pos),
        );
      }
      if (positionFilter === "P") {
        return positions.some((pos) => ["SP", "RP", "P"].includes(pos));
      }
      return positions.includes(positionFilter);
    });
  }, [players, positionFilter]);

  // Sort by contract type when submitted: O → N → B → A → R → Buyout → Release
  const displayPlayers = useMemo(() => {
    if (!isSubmitted) return filteredPlayers;
    return [...filteredPlayers].sort((a, b) => {
      const selA = selections[a.name];
      const selB = selections[b.name];
      const nextA = getNextContract(a.name);
      const nextB = getNextContract(b.name);
      const orderA = getContractSortOrder(nextA, selA?.action, a.contract.contract_type);
      const orderB = getContractSortOrder(nextB, selB?.action, b.contract.contract_type);
      if (orderA !== orderB) return orderA - orderB;
      return b.contract.salary - a.contract.salary;
    });
  }, [filteredPlayers, isSubmitted, selections, getNextContract]);

  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="w-full text-sm">
        <thead className="border-b bg-gray-50">
          <tr>
            <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 sm:px-3">
              守備
            </th>
            <th className="hidden px-2 py-2 text-center text-xs font-medium text-gray-500 sm:table-cell sm:px-3">
              球隊
            </th>
            <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 sm:px-3">
              球員 Player
            </th>
            <th className="px-2 py-2 text-right text-xs font-medium text-gray-500 sm:px-3">
              薪資
            </th>
            <th className="px-2 py-2 text-center text-xs font-medium text-gray-500 sm:px-3">
              合約
            </th>
            <th className="px-2 py-2 text-left text-xs font-medium text-gray-500 sm:px-3">
              動作 Action
            </th>
            <th className="hidden px-2 py-2 text-center text-xs font-medium text-gray-500 sm:table-cell sm:px-3">
              下季
            </th>
          </tr>
        </thead>
        <tbody>
          {displayPlayers.length === 0 && (
            <tr>
              <td
                colSpan={7}
                className="px-3 py-4 text-center text-sm text-gray-400"
              >
                沒有符合條件的球員 No players match this filter
              </td>
            </tr>
          )}
          {displayPlayers.map((player, idx) => {
            const playerOpts = options.find(
              (o) => o.player.name === player.name,
            );
            const sel = selections[player.name];
            const nextContract = getNextContract(player.name);
            const ct = player.contract.contract_type as ContractType;

            const isReleased = sel?.action === "release" || sel?.action === "release_normal";
            const isFA = ct === "O";

            // Group header for submitted sorted view
            const sortOrder = getContractSortOrder(nextContract, sel?.action, ct);
            const prevPlayer = idx > 0 ? displayPlayers[idx - 1] : null;
            const prevOrder = prevPlayer
              ? getContractSortOrder(
                  getNextContract(prevPlayer.name),
                  selections[prevPlayer.name]?.action,
                  prevPlayer.contract.contract_type,
                )
              : -1;
            const showGroupHeader = isSubmitted && sortOrder !== prevOrder;
            const groupCfg = CONTRACT_GROUP_CONFIG[sortOrder] || CONTRACT_GROUP_CONFIG[8];

            return (
              <Fragment key={player.name}>
              {showGroupHeader && (
                <tr>
                  <td
                    colSpan={7}
                    className={`px-2 py-1.5 text-xs font-bold sm:px-3 ${groupCfg.style}`}
                  >
                    {groupCfg.label}
                  </td>
                </tr>
              )}
              <tr
                className={`border-b transition-colors ${
                  isReleased
                    ? "bg-red-50/50 text-gray-400"
                    : isFA
                      ? "bg-gray-50 text-gray-400"
                      : "hover:bg-gray-50"
                }`}
              >
                <td className="px-2 py-2 sm:px-3">
                  <span className="text-xs">{player.position}</span>
                </td>
                <td className="hidden px-2 py-2 text-center sm:table-cell sm:px-3">
                  <span className="text-xs text-gray-500">{player.mlb_team || ""}</span>
                </td>
                <td className="px-2 py-2 font-medium sm:px-3">
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => onPlayerClick(player.name, player.position)}
                      className="text-left text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      {player.name}
                    </button>
                    {mandatoryKeepers.has(player.name) && (
                      <span
                        className="shrink-0 rounded bg-orange-100 px-1 py-0.5 text-[10px] font-semibold text-orange-700"
                        title="FAAB >= $10, must be kept. Release requires buyout."
                      >
                        FAAB$10+
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-2 py-2 text-right sm:px-3">
                  ${player.contract.salary}
                </td>
                <td className="px-2 py-2 text-center sm:px-3">
                  <ContractBadge
                    type={ct}
                    display={player.contract.display}
                  />
                </td>
                <td className="px-2 py-2 sm:px-3">
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
                      className={`w-full min-w-0 sm:min-w-[260px] max-w-[520px] rounded border px-2 py-2.5 text-xs sm:py-1 sm:text-sm ${
                        !sel
                          ? "border-yellow-300 bg-yellow-50"
                          : "border-gray-300"
                      }`}
                    >
                      <option value="">-- 請選擇 --</option>
                      {playerOpts.options.flatMap((opt, i) => {
                        // For N contracts, expand "release" into two buyout options
                        if (ct === "N" && opt.keep_action === "release") {
                          const salary = player.contract.salary;
                          const remaining = player.contract.remaining_years;
                          const faabBuyout = computeBuyoutCost(salary, remaining);
                          const buyoutYrs = faabBuyout.buyoutYears;
                          const mandatoryTag = mandatoryKeepers.has(player.name) ? " (需買斷)" : "";
                          return [
                            <option key={`${i}-faab`} value="release:0">
                              {`買斷 FAAB Buyout: $${faabBuyout.salaryPerYear} Cap + $${faabBuyout.faabPerYear} FAAB/年 x ${buyoutYrs}年${mandatoryTag}`}
                            </option>,
                            <option key={`${i}-normal`} value="release_normal:0">
                              {`買斷 Buyout (全薪資帽): $${salary} Cap/年 x ${buyoutYrs}年${mandatoryTag}`}
                            </option>,
                          ];
                        }
                        const label = getActionLabel(
                          ct,
                          opt.keep_action,
                          opt.extension_years,
                          player.contract.salary,
                        );
                        const isMandatoryRelease =
                          mandatoryKeepers.has(player.name) &&
                          opt.keep_action === "release";
                        return [
                          <option
                            key={i}
                            value={`${opt.keep_action}:${opt.extension_years}`}
                          >
                            {isMandatoryRelease
                              ? `${label} (需買斷 Buyout Required)`
                              : label}
                          </option>,
                        ];
                      })}
                    </select>
                  ) : (
                    <span className="text-gray-500">
                      {sel
                        ? (() => {
                            // N contract buyout: show per-year cost breakdown
                            if (ct === "N" && (sel.action === "release" || sel.action === "release_normal")) {
                              const salary = player.contract.salary;
                              const remaining = player.contract.remaining_years;
                              const buyout = computeBuyoutCost(salary, remaining);
                              const buyoutYrs = buyout.buyoutYears;
                              if (sel.action === "release_normal") {
                                return `買斷 Buyout 全薪資帽 ($${salary} Cap/年 x ${buyoutYrs}年)`;
                              }
                              return `買斷 FAAB Buyout ($${buyout.salaryPerYear} Cap + $${buyout.faabPerYear} FAAB/年 x ${buyoutYrs}年)`;
                            }
                            return getActionLabel(ct, sel.action, sel.extension_years, player.contract.salary);
                          })()
                        : isFA
                          ? "自由球員"
                          : "--"}
                    </span>
                  )}
                </td>
                <td className="hidden px-2 py-2 text-center sm:table-cell sm:px-3">
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
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---- Team Concentration Badges (all players in the section) ----
function TeamConcentrationBadges({ players }: { players: import("@/types").Player[] }) {
  const counts: Record<string, number> = {};
  for (const p of players) {
    if (p.mlb_team) {
      counts[p.mlb_team] = (counts[p.mlb_team] || 0) + 1;
    }
  }
  const concentrated = Object.entries(counts)
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1]);
  if (concentrated.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {concentrated.map(([t, c]) => (
        <span
          key={t}
          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
            c >= 3 ? "bg-amber-200 text-amber-800" : "bg-gray-200 text-gray-600"
          }`}
        >
          {t}:{c}
        </span>
      ))}
    </div>
  );
}
