/**
 * API client for communicating with the FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot connect to backend server. Please check if the server is running.",
    );
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || JSON.stringify(body));
  }

  return res.json();
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
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/api/commissioner/import-excel?year=${year}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
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
  sent: string[];
  skipped: string[];
  failed: Array<{ manager: string; error: string }>;
  no_email: string[];
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
    email: string | null;
    has_email: boolean;
  }>;
}> {
  return request(`/api/commissioner/reminders/${year}/pending`);
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
