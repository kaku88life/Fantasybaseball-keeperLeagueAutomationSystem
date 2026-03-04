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

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

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

export async function loginWithYahoo(): Promise<{ auth_url: string }> {
  return request("/api/auth/yahoo/login", { method: "POST" });
}

export async function authCallback(
  code: string,
  state: string,
): Promise<{ token: string; user: import("@/types").UserInfo }> {
  return request(`/api/auth/yahoo/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`);
}

export async function getCurrentUser(): Promise<import("@/types").UserInfo> {
  return request("/api/auth/me");
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
    bench_keepers: number;
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
