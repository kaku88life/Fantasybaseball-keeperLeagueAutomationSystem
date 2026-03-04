// Contract and Player types matching Python models

export type ContractType = "A" | "B" | "N" | "O" | "R" | "FA";

export interface Contract {
  contract_type: ContractType;
  salary: number;
  extension_years: number;
  display: string;
  remaining_years: number;
  is_keepable: boolean;
  special_status: string;
}

export interface BuyoutRecord {
  player_name: string;
  original_contract: string;
  buyout_salary_cost: number;
  buyout_faab_cost: number;
  remaining_years: number;
  use_faab: boolean;
  note: string;
  display: string;
}

export interface Player {
  name: string;
  position: string;
  contract: Contract;
  yahoo_player_id: string | null;
  is_active_keeper: boolean;
}

export interface Team {
  id: number | null;
  manager_name: string;
  team_name: string;
  yahoo_team_id: string | null;
  players: Player[];
  buyout_records: BuyoutRecord[];
  salary_cap: number;
  faab_budget: number;
  ranking_bonus: number;
  trade_compensation: number;
  previous_rank: number | null;
  total_keeper_cost: number;
  total_buyout_cost: number;
  total_buyout_faab_cost: number;
  available_salary: number;
  available_faab: number;
  active_keeper_count: number;
  bench_keeper_count: number;
}

export interface LeagueSnapshot {
  year: number;
  salary_cap: number;
  teams: Team[];
}

// Keeper options / transitions
export interface ContractTransition {
  player_name: string;
  current_contract: string;
  next_contract: string | null;
  action: string;
  salary_change: number;
  is_mandatory: boolean;
  keep_action: string;
  extension_years: number;
}

export interface PlayerKeeperOptions {
  player: Player;
  options: ContractTransition[];
}

// Keeper selections
export interface KeeperSelection {
  player_name: string;
  current_contract: string;
  action: string;
  extension_years: number;
  next_contract: string | null;
}

export interface FinancialSummary {
  salary_cap: number;
  ranking_bonus: number;
  trade_compensation: number;
  keeper_cost: number;
  buyout_salary_cost: number;
  available_salary: number;
  faab_budget: number;
  buyout_faab_cost: number;
  available_faab: number;
  active_keeper_count: number;
  bench_keeper_count: number;
}

export interface ValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  financial_summary: FinancialSummary | null;
}

export interface KeeperSelectionsWithValidation {
  selections: KeeperSelection[];
  validation: ValidationResult;
  is_submitted: boolean;
}

// Auth
export interface UserInfo {
  user_id: number;
  yahoo_guid: string;
  yahoo_nickname: string;
  team_id: number | null;
  team_name: string | null;
  manager_name: string | null;
  is_commissioner: boolean;
}

// Commissioner
export interface SubmissionStatus {
  team_id: number;
  manager_name: string;
  team_name: string;
  is_submitted: boolean;
  submitted_at: string | null;
  is_valid: boolean;
  commissioner_approved: boolean;
  commissioner_notes: string;
}

// League settings
export interface LeagueSettings {
  league_name: string;
  total_teams: number;
  scoring_format: string;
  hitting_cats: string[];
  pitching_cats: string[];
  salary_base: number;
  salary_increment: number;
  faab_base: number;
  min_bid: number;
  keeper_active_min: number;
  keeper_active_max: number;
  keeper_bench_max: number;
  extension_cost_per_year: number;
  contract_types: string[];
  ranking_bonus: Record<number, number>;
  roster_positions: Record<string, string[]>;
}

// DB team record
export interface DBTeam {
  id: number;
  manager_name: string;
  team_name: string;
  yahoo_team_id: string;
}
