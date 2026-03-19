/**
 * API client for communicating with the FastAPI backend.
 */

import type { BuyoutRecord } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

/** Default request timeout in milliseconds (30 seconds — allows for Zeabur cold start) */
const REQUEST_TIMEOUT_MS = 30_000;

async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // iOS Safari / LINE browser fallback: add Authorization header from localStorage
  // when cross-origin cookies are blocked by ITP
  if (typeof window !== "undefined") {
    const fallbackToken = localStorage.getItem("auth_token_fallback");
    if (fallbackToken && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${fallbackToken}`;
    }
  }

  // AbortController for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",   // Send HttpOnly auth cookie
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        "Request timed out. The server may be starting up (cold start). Please try again in a few seconds.",
      );
    }
    throw new ApiError(
      0,
      "Cannot connect to backend server. Please check if the server is running.",
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || JSON.stringify(body));
  }

  return res.json();
}

/**
 * Check if backend is reachable (health check).
 * Returns true if healthy, false otherwise.
 */
export async function checkHealth(): Promise<boolean> {
  try {
    await request<{ status: string }>("/api/health", {}, 10_000);
    return true;
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ========== Auth ==========

export async function getCurrentUser(): Promise<import("@/types").UserInfo> {
  return request("/api/auth/me");
}

export async function updateLineName(lineName: string): Promise<{ message: string; line_name: string }> {
  return request("/api/auth/line-name", {
    method: "PUT",
    body: JSON.stringify({ line_name: lineName }),
  });
}

// ========== League ==========

export async function getYears(): Promise<number[]> {
  return request("/api/league/years");
}

export async function getLeagueYear(year: number): Promise<import("@/types").LeagueSnapshot> {
  return request(`/api/league/${year}`);
}

export async function getLeagueSummary(year: number): Promise<{
  year: number;
  salary_cap: number;
  teams: Array<{
    manager_name: string;
    team_name: string;
    active_keepers: number;
    farm_rookies: number;
    total_keeper_cost: number;
    available_salary: number;
    available_faab: number;
    salary_cap: number;
    ranking_bonus: number;
  }>;
}> {
  return request(`/api/league/${year}/summary`);
}

export async function getLeagueSettings(): Promise<import("@/types").LeagueSettings> {
  return request("/api/league/settings");
}

export interface KeptPlayer {
  player_name: string;
  current_contract: string;
  next_contract: string;
  action: string;
  salary: number;
  position: string;
  mlb_team: string;
}

export interface KeeperResultTeam {
  team_id: number;
  manager_name: string;
  team_name: string;
  line_name?: string;
  is_submitted: boolean;
  kept_players: KeptPlayer[];
  keeper_cost: number;
  buyout_cost: number;
  buyout_faab_cost: number;
  ranking_bonus: number;
  trade_compensation: number;
  salary_cap: number;
  available_salary: number;
  faab_budget: number;
  available_faab: number;
}

export async function getKeeperResults(year: number): Promise<{
  year: number;
  teams: KeeperResultTeam[];
}> {
  return request(`/api/league/${year}/keeper-results`);
}

// ========== Teams ==========

export async function getTeams(): Promise<import("@/types").DBTeam[]> {
  return request("/api/teams/");
}

export async function getTeamRoster(
  teamId: number,
  year: number,
): Promise<import("@/types").Team> {
  return request(`/api/teams/${teamId}/roster/${year}`);
}

export async function getKeeperOptions(
  teamId: number,
  year: number,
): Promise<import("@/types").PlayerKeeperOptions[]> {
  return request(`/api/teams/${teamId}/keeper-options/${year}`);
}

export async function getKeeperPageData(
  teamId: number,
  year: number,
): Promise<{
  roster: import("@/types").Team;
  options: import("@/types").PlayerKeeperOptions[];
  selections: import("@/types").KeeperSelectionsWithValidation;
}> {
  return request(`/api/teams/${teamId}/keeper-page/${year}`);
}

export async function getKeeperSelections(
  teamId: number,
  year: number,
): Promise<import("@/types").KeeperSelectionsWithValidation> {
  return request(`/api/teams/${teamId}/keeper-selections/${year}`);
}

export async function updateKeeperSelections(
  teamId: number,
  year: number,
  selections: Array<{ player_name: string; action: string; extension_years?: number }>,
): Promise<import("@/types").KeeperSelectionsWithValidation> {
  return request(`/api/teams/${teamId}/keeper-selections/${year}`, {
    method: "PUT",
    body: JSON.stringify({ selections }),
  });
}

export async function submitKeeperList(
  teamId: number,
  year: number,
): Promise<{ message: string }> {
  return request(`/api/teams/${teamId}/keeper-submit/${year}`, {
    method: "POST",
  });
}

// ========== Commissioner ==========

export async function getSubmissions(year: number): Promise<import("@/types").SubmissionStatus[]> {
  return request(`/api/commissioner/submissions/${year}`);
}

export async function approveSubmission(
  year: number,
  teamId: number,
  approved: boolean,
  notes: string = "",
): Promise<{ message: string }> {
  return request(`/api/commissioner/approve/${year}/${teamId}`, {
    method: "POST",
    body: JSON.stringify({ approved, notes }),
  });
}

export async function getSubmissionDetail(
  year: number,
  teamId: number,
): Promise<import("@/types").SubmissionDetail> {
  return request(`/api/commissioner/submissions/${year}/${teamId}`);
}

export async function unlockSubmission(
  year: number,
  teamId: number,
): Promise<{ message: string }> {
  return request(`/api/commissioner/unlock/${year}/${teamId}`, {
    method: "POST",
  });
}

export async function getUsers(): Promise<import("@/types").UserWithTeam[]> {
  return request("/api/commissioner/users");
}

export async function assignTeam(
  userId: number,
  teamId: number,
): Promise<{ message: string }> {
  return request("/api/commissioner/assign-team", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, team_id: teamId }),
  });
}

export async function setCommissioner(userId: number): Promise<{ message: string }> {
  return request(`/api/commissioner/set-commissioner/${userId}`, {
    method: "POST",
  });
}

export async function verifyCommissionerPassword(
  password: string,
): Promise<{ message: string; token: string }> {
  return request("/api/auth/commissioner-verify", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export async function updateUserLineName(
  userId: number,
  lineName: string,
): Promise<{ message: string }> {
  return request(`/api/commissioner/users/${userId}/line-name`, {
    method: "PUT",
    body: JSON.stringify({ line_name: lineName }),
  });
}

export async function deleteUser(userId: number): Promise<{ message: string }> {
  return request(`/api/commissioner/users/${userId}`, {
    method: "DELETE",
  });
}

export async function clearKeeperSelections(
  year: number,
  teamId: number,
): Promise<{ message: string }> {
  return request(`/api/commissioner/keeper-selections/${year}/${teamId}`, {
    method: "DELETE",
  });
}

export async function getAllTeamAdjustments(): Promise<import("@/types").TeamAdjustments[]> {
  return request("/api/commissioner/all-team-adjustments");
}

export async function updateTeamAdjustments(
  teamId: number,
  tradeCompensation: number,
  faabAdjustment: number,
): Promise<{ message: string }> {
  return request(`/api/commissioner/team-adjustments/${teamId}`, {
    method: "PUT",
    body: JSON.stringify({
      trade_compensation: tradeCompensation,
      faab_adjustment: faabAdjustment,
    }),
  });
}

export async function importExcel(file: File, year: number): Promise<{
  year: number;
  teams_count: number;
  teams: string[];
  message: string;
}> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/commissioner/import-excel?year=${year}`, {
    method: "POST",
    credentials: "include",   // Send HttpOnly auth cookie
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || JSON.stringify(body));
  }

  return res.json();
}

// ========== Keeper Reminders ==========

export async function sendReminders(year: number): Promise<{
  sent_to_group: boolean;
  pending_managers: string[];
  skipped_reason: string | null;
  error: string | null;
}> {
  return request(`/api/commissioner/reminders/${year}/send`, {
    method: "POST",
  });
}

export async function getReminderStatus(year: number): Promise<{
  year: number;
  history: Array<{
    id: number;
    team_id: number;
    manager_name: string;
    notification_type: string;
    channel: string;
    recipient_email: string;
    sent_at: string;
    sent_by: string;
    status: string;
    error_message: string;
  }>;
}> {
  return request(`/api/commissioner/reminders/${year}/status`);
}

export async function getPendingTeams(year: number): Promise<{
  year: number;
  pending_count: number;
  teams: Array<{
    id: number;
    manager_name: string;
  }>;
}> {
  return request(`/api/commissioner/reminders/${year}/pending`);
}

export async function testLineConnection(): Promise<{
  success: boolean;
  message: string;
  group_id: string | null;
}> {
  return request(`/api/commissioner/line/test`, {
    method: "POST",
  });
}

// ========== Buyout Management (Commissioner) ==========

export async function getAllBuyouts(year: number): Promise<{
  year: number;
  buyouts: Array<BuyoutRecord & { manager_name: string }>;
  total_count: number;
}> {
  return request(`/api/commissioner/buyouts/${year}`);
}

export async function getTeamBuyouts(
  year: number,
  teamId: number,
): Promise<{
  year: number;
  team_id: number;
  manager_name: string;
  buyouts: BuyoutRecord[];
}> {
  return request(`/api/commissioner/buyouts/${year}/${teamId}`);
}

export async function createBuyout(data: {
  team_id: number;
  year: number;
  player_name: string;
  original_contract: string;
  buyout_salary: number;
  buyout_faab?: number;
  buyout_years: number;
  remaining_years: number;
  buyout_type?: string;
  use_faab?: boolean;
  notes?: string;
}): Promise<{ message: string; buyout: BuyoutRecord }> {
  return request("/api/commissioner/buyouts", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateBuyout(
  buyoutId: number,
  data: Partial<{
    player_name: string;
    original_contract: string;
    buyout_salary: number;
    buyout_faab: number;
    buyout_years: number;
    remaining_years: number;
    buyout_type: string;
    use_faab: boolean;
    notes: string;
  }>,
): Promise<{ message: string; buyout: BuyoutRecord }> {
  return request(`/api/commissioner/buyouts/${buyoutId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteBuyout(buyoutId: number): Promise<{ message: string }> {
  return request(`/api/commissioner/buyouts/${buyoutId}`, { method: "DELETE" });
}

// ========== Player Database (Public) ==========

export interface PlayerDatabaseParams {
  page?: number;
  page_size?: number;
  search?: string;
  position?: string;
  owner?: string;
  contract?: string;
  player_type?: string;
  mlb_team?: string;
  sort_key?: string;
  sort_dir?: string;
}

export async function getPlayerDatabase(
  year: number,
  params: PlayerDatabaseParams = {},
): Promise<import("@/types").PlayerDatabaseResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "" && v !== null) qs.set(k, String(v));
  }
  const query = qs.toString();
  return request(`/api/players/database/${year}${query ? `?${query}` : ""}`);
}

// ========== Player Rankings (Commissioner) ==========

export async function fetchYahooRankings(
  year: number,
  sortType: string = "season",
): Promise<{
  message: string;
  year: number;
  total_fetched: number;
  ar_fetched: number;
  sort_type: string;
  errors: string[] | null;
}> {
  // Longer timeout for batch Yahoo API calls (~80 requests: OR + AR x 1000 players)
  return request(
    `/api/commissioner/fetch-rankings/${year}?sort_type=${encodeURIComponent(sortType)}`,
    { method: "POST" },
    300_000,
  );
}

export async function getRankingFetchStatus(
  year: number,
): Promise<import("@/types").RankingFetchStatus> {
  return request(`/api/commissioner/ranking-status/${year}`);
}

// ========== Top 100 Prospects ==========

export async function getProspects(
  year: number,
): Promise<import("@/types").ProspectsResponse> {
  return request(`/api/players/prospects/${year}`);
}

export async function reloadProspects(): Promise<{
  message: string;
  count: number;
  source: string;
  updated_at: string;
}> {
  return request("/api/commissioner/reload-prospects", { method: "POST" });
}

// ========== Player Stats (MLB Stats API) ==========

export async function getPlayerStats(
  name: string,
  position: string = "",
): Promise<import("@/types").PlayerStats> {
  const params = new URLSearchParams({ name });
  if (position) params.set("position", position);
  return request(`/api/players/stats?${params.toString()}`);
}

// ========== Validation ==========

export async function validateKeeperList(
  teamId: number,
  year: number,
  selections: Array<{ player_name: string; action: string; extension_years?: number }>,
): Promise<import("@/types").ValidationResult> {
  return request("/api/validate/keeper-list", {
    method: "POST",
    body: JSON.stringify({ team_id: teamId, year, selections }),
  });
}

// ========== Yahoo API Token (Commissioner) ==========

export interface YahooTokenStatus {
  connected: boolean;
  user_id: number | null;
  yahoo_guid: string;
  expires_at: string | null;
  is_expired: boolean;
  updated_at: string | null;
  message: string;
}

export async function getYahooTokenStatus(): Promise<YahooTokenStatus> {
  return request("/api/commissioner/yahoo-token/status");
}

export async function refreshYahooToken(): Promise<YahooTokenStatus> {
  return request("/api/commissioner/yahoo-token/refresh", { method: "POST" });
}

export async function testYahooConnection(): Promise<{ status: string; message: string }> {
  return request("/api/commissioner/yahoo-token/test", { method: "POST" });
}

export async function disconnectYahooToken(): Promise<{ message: string }> {
  return request("/api/commissioner/yahoo-token", { method: "DELETE" });
}

// ========== Analytics ==========

export async function getDraftStats(years?: number[]): Promise<DraftStatsResponse> {
  const params = years?.length ? `?years=${years.join(",")}` : "";
  return request(`/api/analytics/draft-stats${params}`);
}

export async function getFaabStats(years?: number[]): Promise<FaabStatsResponse> {
  const params = years?.length ? `?years=${years.join(",")}` : "";
  return request(`/api/analytics/faab-stats${params}`);
}

export async function getPositionPreference(
  years?: number[],
  minCost: number = 20,
): Promise<PositionPreferenceResponse> {
  const yearParam = years?.length ? `years=${years.join(",")}&` : "";
  return request(`/api/analytics/position-preference?${yearParam}min_cost=${minCost}`);
}

export async function fetchDraftData(year: number): Promise<{
  year: number;
  league_key: string;
  files_written: string[];
  draft_picks?: number;
  transactions?: number;
  faab_budget?: number;
}> {
  return request(`/api/commissioner/fetch-draft-data/${year}`, { method: "POST" });
}

export async function getAvailableDraftYears(): Promise<{ years: number[] }> {
  return request("/api/commissioner/draft-data/available-years");
}

export interface DraftPick {
  player: string;
  cost: number;
  round: number;
  pick: number;
  position: string;
}

export interface DraftStatsResponse {
  years: number[];
  teams: Record<string, {
    yearly: Record<string, {
      top_picks: DraftPick[];
      top10_total: number;
      total_spent: number;
      players_drafted: number;
    }>;
  }>;
  yearly_summary: Record<string, {
    team_count: number;
    league_max: { cost: number; player: string; manager: string };
  }>;
}

export interface FaabStatsResponse {
  years: number[];
  teams: Record<string, {
    yearly: Record<string, {
      total_faab_spent: number;
      faab_budget: number;
      remaining: number;
      remaining_pct: number;
      num_pickups: number;
      avg_bid: number;
      max_bid: number;
      max_bid_player: string;
    }>;
  }>;
  yearly_summary: Record<string, {
    faab_budget: number;
    total_league_faab_spent: number;
    avg_team_faab_spent: number;
    team_count: number;
  }>;
}

export interface PositionPreferenceResponse {
  years: number[];
  min_cost: number;
  teams: Record<string, {
    yearly: Record<string, {
      picks: Array<{ player: string; position: string; pos_category: string; cost: number }>;
      position_breakdown: Record<string, number>;
      total_picks: number;
      total_spent: number;
    }>;
    career_position_breakdown: Record<string, number>;
  }>;
  league_position_breakdown: Record<string, number>;
}

export interface TradeDetail {
  partner: string;
  received: string[];
  sent: string[];
  timestamp: string;
}

export interface TradeStatsResponse {
  years: number[];
  teams: Record<string, {
    yearly: Record<string, {
      trade_count: number;
      players_received: string[];
      players_sent: string[];
      trades: TradeDetail[];
    }>;
  }>;
  yearly_summary: Record<string, {
    total_trades: number;
    team_count: number;
  }>;
}

export async function getTradeStats(years?: number[]): Promise<TradeStatsResponse> {
  const params = years?.length ? `?years=${years.join(",")}` : "";
  return request(`/api/analytics/trade-stats${params}`);
}

// --- Salary Rankings ---

export interface SalaryRankingEntry {
  rank: number;
  player: string;
  salary: number;
  contract_type: string;
  manager: string;
  source: string;
  position: string;
  salary_pct: number;
}

export interface SalaryRankingsResponse {
  years: number[];
  rankings: Record<string, SalaryRankingEntry[]>;
}

export async function getSalaryRankings(years?: number[]): Promise<SalaryRankingsResponse> {
  const params = years?.length ? `?years=${years.join(",")}` : "";
  return request(`/api/analytics/salary-rankings${params}`);
}

// --- Contract Values ---

export interface ContractValue {
  player: string;
  salary: number;
  original_n: number;
  total_years: number;
  total_value: number;
  first_seen_year: number;
  first_seen_contract: string;
  current_contract: string;
  current_year: number;
  manager: string;
  manager_history: string[];
  years_remaining: number;
}

export interface ContractValuesResponse {
  contracts: ContractValue[];
}

export async function getContractValues(): Promise<ContractValuesResponse> {
  return request("/api/analytics/contract-values");
}

// --- League Summary ---

export interface LeagueSummaryResponse {
  keeper_stats: Record<
    string,
    {
      teams: Array<{
        manager: string;
        keeper_count: number;
        total_cost: number;
        avg_cost: number;
      }>;
      league_avg_cost: number;
      highest_spender: { manager: string; total_cost: number } | null;
      lowest_spender: { manager: string; total_cost: number } | null;
    }
  >;
  draft_highlights: Record<
    string,
    {
      total_picks: number;
      total_spent: number;
      avg_pick_cost: number;
      max_pick: number;
      biggest_spender: { manager: string; total: number };
    }
  >;
  contract_highlights: {
    top5: ContractValue[];
    total_n_contracts: number;
    total_committed_value: number;
  };
  trade_highlights: Record<
    string,
    {
      trade_count: number;
      faab_transactions: number;
      total_transactions: number;
    }
  >;
}

export async function getLeagueAnalyticsSummary(): Promise<LeagueSummaryResponse> {
  return request("/api/analytics/league-summary");
}

// ========== Validation ==========

export async function calculateBuyout(
  playerName: string,
  contractType: string,
  salary: number,
  extensionYears: number = 0,
  useFaab: boolean = false,
): Promise<{
  player_name: string;
  total_cost: number;
  salary_cap_cost: number;
  faab_cost: number;
  remaining_years: number;
  yearly_breakdown: Array<{ year: number; salary_cap: number; faab: number; total: number }>;
}> {
  return request("/api/validate/buyout-calculation", {
    method: "POST",
    body: JSON.stringify({
      player_name: playerName,
      contract_type: contractType,
      salary,
      extension_years: extensionYears,
      use_faab: useFaab,
    }),
  });
}
