"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  getKeeperOptions,
  getKeeperSelections,
  getTeamRoster,
  submitKeeperList,
  updateKeeperSelections,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ContractBadge from "@/components/ContractBadge";
import type {
  ContractType,
  KeeperSelection,
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
  const [selections, setSelections] = useState<
    Record<string, { action: string; extension_years: number }>
  >({});
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const isOwnTeam = user?.team_id === teamId;
  const canEdit = isOwnTeam || user?.is_commissioner;

  // Load data
  useEffect(() => {
    if (!year || !teamId) return;

    Promise.all([
      getTeamRoster(teamId, year),
      getKeeperOptions(teamId, year),
    ])
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
        const sel: Record<
          string,
          { action: string; extension_years: number }
        > = {};
        for (const s of data.selections) {
          sel[s.player_name] = {
            action: s.action,
            extension_years: s.extension_years,
          };
        }
        setSelections(sel);
        setValidation(data.validation);
        setIsSubmitted(data.is_submitted);
      })
      .catch(() => {
        // No saved selections yet
      });
  }, [year, teamId, user]);

  // Update a single player's selection
  const updateSelection = useCallback(
    (playerName: string, action: string, extensionYears: number = 0) => {
      setSelections((prev) => ({
        ...prev,
        [playerName]: { action, extension_years: extensionYears },
      }));
    },
    [],
  );

  // Save all selections
  const handleSave = useCallback(async () => {
    setSaving(true);
    setMessage("");
    try {
      const sels = Object.entries(selections).map(([name, s]) => ({
        player_name: name,
        action: s.action,
        extension_years: s.extension_years,
      }));
      const result = await updateKeeperSelections(teamId, year, sels);
      setValidation(result.validation);
      setMessage("Saved successfully");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [selections, teamId, year]);

  // Submit keeper list
  const handleSubmit = useCallback(async () => {
    if (!confirm("Are you sure you want to submit your keeper list? This will lock your selections.")) {
      return;
    }
    setSubmitting(true);
    try {
      // Save first
      const sels = Object.entries(selections).map(([name, s]) => ({
        player_name: name,
        action: s.action,
        extension_years: s.extension_years,
      }));
      await updateKeeperSelections(teamId, year, sels);
      await submitKeeperList(teamId, year);
      setIsSubmitted(true);
      setMessage("Keeper list submitted successfully!");
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

  // Financial summary from validation
  const fin = validation?.financial_summary;

  if (error && !team) {
    return (
      <div className="py-10 text-center">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!team) {
    return <div className="py-10 text-center text-gray-500">Loading...</div>;
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold">
          {team.manager_name} - {year} Keeper Selection
        </h1>
        {team.team_name && (
          <p className="text-sm text-gray-500">{team.team_name}</p>
        )}
        {isSubmitted && (
          <span className="mt-1 inline-block rounded bg-green-100 px-2 py-0.5 text-sm text-green-800">
            Submitted
          </span>
        )}
      </div>

      {/* Financial Summary */}
      {fin && (
        <div className="mb-6 grid grid-cols-2 gap-3 rounded-lg border bg-white p-4 md:grid-cols-4">
          <div>
            <p className="text-xs text-gray-500">Salary Cap</p>
            <p className="text-lg font-bold">${fin.salary_cap}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Ranking Bonus</p>
            <p className="text-lg font-bold text-yellow-600">
              +${fin.ranking_bonus}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Keeper Cost</p>
            <p className="text-lg font-bold">${fin.keeper_cost}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Available Salary</p>
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
          <div>
            <p className="text-xs text-gray-500">FAAB Budget</p>
            <p className="text-lg font-bold">${fin.faab_budget}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Buyout FAAB</p>
            <p className="text-lg font-bold">${fin.buyout_faab_cost}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Active Keepers</p>
            <p className="text-lg font-bold">
              {fin.active_keeper_count}/10
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Bench (R)</p>
            <p className="text-lg font-bold">
              {fin.bench_keeper_count}/2
            </p>
          </div>
        </div>
      )}

      {/* Validation Messages */}
      {validation && (
        <div className="mb-4 space-y-2">
          {validation.errors.map((e, i) => (
            <div
              key={i}
              className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {e}
            </div>
          ))}
          {validation.warnings.map((w, i) => (
            <div
              key={i}
              className="rounded border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-700"
            >
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Player Table */}
      <div className="overflow-x-auto rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left">Position</th>
              <th className="px-3 py-2 text-left">Player</th>
              <th className="px-3 py-2 text-left">Salary</th>
              <th className="px-3 py-2 text-left">Contract</th>
              <th className="px-3 py-2 text-left">Action</th>
              <th className="px-3 py-2 text-left">Next Contract</th>
            </tr>
          </thead>
          <tbody>
            {team.players.map((player) => {
              const playerOpts = options.find(
                (o) => o.player.name === player.name,
              );
              const sel = selections[player.name];
              const nextContract = getNextContract(player.name);
              const ct = player.contract.contract_type as ContractType;

              return (
                <tr
                  key={player.name}
                  className={`border-b ${
                    sel?.action === "release" ? "bg-red-50 opacity-60" : ""
                  } ${ct === "O" ? "bg-gray-50 opacity-60" : ""}`}
                >
                  <td className="px-3 py-2">
                    <span className="text-xs text-gray-500">
                      {player.position}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-medium">{player.name}</td>
                  <td className="px-3 py-2">${player.contract.salary}</td>
                  <td className="px-3 py-2">
                    <ContractBadge
                      type={ct}
                      display={player.contract.display}
                    />
                  </td>
                  <td className="px-3 py-2">
                    {canEdit && !isSubmitted && playerOpts ? (
                      <select
                        value={
                          sel
                            ? `${sel.action}:${sel.extension_years}`
                            : ""
                        }
                        onChange={(e) => {
                          const [action, ext] = e.target.value.split(":");
                          updateSelection(
                            player.name,
                            action,
                            Number(ext) || 0,
                          );
                        }}
                        className="rounded border px-2 py-1 text-sm"
                      >
                        <option value="">-- Select --</option>
                        {playerOpts.options.map((opt, i) => (
                          <option
                            key={i}
                            value={`${opt.keep_action}:${opt.extension_years}`}
                          >
                            {opt.action}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-gray-500">
                        {sel?.action || (ct === "O" ? "FA" : "--")}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {nextContract ? (
                      nextContract === "FA" ? (
                        <span className="text-gray-400">FA</span>
                      ) : (
                        <span className="font-medium text-indigo-600">
                          {nextContract}
                        </span>
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

      {/* Buyout Records */}
      {team.buyout_records.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">
            Buyout Records
          </h3>
          <div className="overflow-x-auto rounded border bg-white">
            <table className="w-full text-sm">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left">Player</th>
                  <th className="px-3 py-2 text-left">Contract</th>
                  <th className="px-3 py-2 text-left">Salary Cost</th>
                  <th className="px-3 py-2 text-left">FAAB Cost</th>
                </tr>
              </thead>
              <tbody>
                {team.buyout_records.map((b) => (
                  <tr key={b.player_name} className="border-b">
                    <td className="px-3 py-2">{b.player_name}</td>
                    <td className="px-3 py-2">{b.original_contract}</td>
                    <td className="px-3 py-2">${b.buyout_salary_cost}</td>
                    <td className="px-3 py-2">${b.buyout_faab_cost}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {canEdit && !isSubmitted && (
        <div className="mt-6 flex items-center gap-4">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-gray-700 px-4 py-2 text-white hover:bg-gray-600 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !validation?.is_valid}
            className="rounded bg-green-600 px-4 py-2 text-white hover:bg-green-500 disabled:opacity-50"
          >
            {submitting ? "Submitting..." : "Submit Keeper List"}
          </button>
          {message && <span className="text-sm text-green-600">{message}</span>}
          {error && <span className="text-sm text-red-600">{error}</span>}
        </div>
      )}
    </div>
  );
}
