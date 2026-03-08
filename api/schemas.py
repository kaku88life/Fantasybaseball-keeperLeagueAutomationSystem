"""
Fantasy Baseball Keeper League - Pydantic Request/Response Models

Mirrors the dataclasses in src/contract/models.py for JSON serialization.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ========== Contract / Player / Team schemas ==========

class ContractSchema(BaseModel):
    contract_type: str  # "A", "B", "N", "O", "R", "FA"
    salary: int
    extension_years: int = 0
    display: str = ""
    remaining_years: int = 0
    is_keepable: bool = True
    special_status: str = "none"


class BuyoutRecordSchema(BaseModel):
    player_name: str
    original_contract: str
    buyout_salary_cost: int
    buyout_faab_cost: int
    remaining_years: int
    use_faab: bool = False
    note: str = ""
    display: str = ""


class PlayerSchema(BaseModel):
    name: str
    position: str
    contract: ContractSchema
    yahoo_player_id: Optional[str] = None
    is_active_keeper: bool = True


class TeamSchema(BaseModel):
    id: Optional[int] = None  # DB id
    manager_name: str
    team_name: str
    yahoo_team_id: Optional[str] = None
    players: list[PlayerSchema] = []
    buyout_records: list[BuyoutRecordSchema] = []
    # Financial
    salary_cap: int = 0
    faab_budget: int = 0
    ranking_bonus: int = 0
    trade_compensation: int = 0
    previous_rank: Optional[int] = None
    # Computed
    total_keeper_cost: int = 0
    total_buyout_cost: int = 0
    total_buyout_faab_cost: int = 0
    available_salary: int = 0
    available_faab: int = 0
    active_keeper_count: int = 0
    bench_keeper_count: int = 0


class LeagueSnapshotSchema(BaseModel):
    year: int
    salary_cap: int
    teams: list[TeamSchema] = []


# ========== Keeper Options / Transitions ==========

class ContractTransitionSchema(BaseModel):
    player_name: str
    current_contract: str  # display string
    next_contract: Optional[str] = None  # display string or None (FA)
    action: str
    salary_change: int = 0
    is_mandatory: bool = False
    keep_action: str = ""  # "keep", "extend", "release", "activate"
    extension_years: int = 0


class PlayerKeeperOptionsSchema(BaseModel):
    player: PlayerSchema
    options: list[ContractTransitionSchema]


# ========== Keeper Selection ==========

class KeeperSelectionInput(BaseModel):
    player_name: str
    action: str  # "keep", "extend", "release", "activate"
    extension_years: int = 0


class KeeperSelectionsUpdate(BaseModel):
    selections: list[KeeperSelectionInput]


class KeeperSelectionResponse(BaseModel):
    player_name: str
    current_contract: str
    action: str
    extension_years: int = 0
    next_contract: Optional[str] = None


# ========== Validation ==========

class FinancialSummary(BaseModel):
    salary_cap: int = 0
    ranking_bonus: int = 0
    trade_compensation: int = 0
    keeper_cost: int = 0
    buyout_salary_cost: int = 0
    available_salary: int = 0
    faab_budget: int = 0
    faab_adjustment: int = 0
    buyout_faab_cost: int = 0
    available_faab: int = 0
    active_keeper_count: int = 0
    bench_keeper_count: int = 0


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    financial_summary: Optional[FinancialSummary] = None


class KeeperSelectionsWithValidation(BaseModel):
    selections: list[KeeperSelectionResponse]
    validation: ValidationResult
    is_submitted: bool = False


# ========== Commissioner ==========

class ImportExcelResponse(BaseModel):
    year: int
    teams_count: int
    teams: list[str]  # manager names
    message: str


class SubmissionStatusSchema(BaseModel):
    team_id: int
    manager_name: str
    team_name: str
    is_submitted: bool
    submitted_at: Optional[str] = None
    is_valid: bool = False
    commissioner_approved: bool = False
    commissioner_notes: str = ""


class ApproveRequest(BaseModel):
    approved: bool
    notes: str = ""


class AssignTeamRequest(BaseModel):
    user_id: int
    team_id: int


class TeamAdjustmentsRequest(BaseModel):
    trade_compensation: int = 0
    faab_adjustment: int = 0


# ========== Auth ==========

class LoginResponse(BaseModel):
    auth_url: str


class CallbackResponse(BaseModel):
    token: str
    user: UserInfoSchema


class UserInfoSchema(BaseModel):
    user_id: int
    yahoo_guid: str
    yahoo_nickname: str
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    manager_name: Optional[str] = None
    is_commissioner: bool = False


# ========== League Settings ==========

class LeagueSettingsSchema(BaseModel):
    league_name: str
    total_teams: int
    scoring_format: str
    hitting_cats: list[str]
    pitching_cats: list[str]
    salary_base: int
    salary_increment: int
    faab_base: int
    min_bid: int
    keeper_active_min: int
    keeper_active_max: int
    keeper_bench_max: int
    extension_cost_per_year: int
    contract_types: list[str]
    ranking_bonus: dict[int, int]
    roster_positions: dict[str, list[str]]
