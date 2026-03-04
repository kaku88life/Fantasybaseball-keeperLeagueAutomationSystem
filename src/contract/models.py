"""
Fantasy Baseball Keeper League - Data Models
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContractType(Enum):
    A = "A"       # 1st year (draft / FAAB pickup)
    B = "B"       # 2nd year (A kept)
    N = "N"       # Extension year (N+O, salary + N*$5)
    O = "O"       # Option year (final year, then FA)
    R = "R"       # Rookie (bench only, doesn't count toward 10-man limit)
    FA = "FA"     # Free agent (not on any team)


class SpecialStatus(Enum):
    NONE = "none"
    LEGAL_ISSUE = "legal_issue"     # domestic violence, scandal
    RETIRED = "retired"             # retired during prime
    LIFETIME_BAN = "lifetime_ban"   # lifetime ban


@dataclass
class Contract:
    """Represents a player's contract state."""
    contract_type: ContractType
    salary: int
    extension_years: int = 0        # N value (e.g., N3 means 3 years of extension remaining)
    special_status: SpecialStatus = SpecialStatus.NONE

    @property
    def display(self) -> str:
        """Human-readable contract string like '$20/N3' or '$10/O'."""
        if self.contract_type == ContractType.N:
            return f"${self.salary}/N{self.extension_years}"
        return f"${self.salary}/{self.contract_type.value}"

    @property
    def remaining_years(self) -> int:
        """Total remaining contract years including current year.
        A: 1 year (current) -> can keep as B
        B: 1 year (current) -> can keep as O or N+O
        N(x): x years of N + 1 year of O remaining
        O: 1 year (current) -> FA after
        R: indefinite while rookie-eligible
        """
        if self.contract_type == ContractType.A:
            return 1
        if self.contract_type == ContractType.B:
            return 1
        if self.contract_type == ContractType.N:
            return self.extension_years + 1  # N years + O year
        if self.contract_type == ContractType.O:
            return 1
        if self.contract_type == ContractType.R:
            return 0  # indefinite
        return 0

    @property
    def is_keepable(self) -> bool:
        """Whether this player can be kept for next season."""
        return self.contract_type not in (ContractType.O, ContractType.FA)

    @property
    def is_special_clause_active(self) -> bool:
        """Whether special clause (no salary, no roster spot) is active."""
        return self.special_status != SpecialStatus.NONE


@dataclass
class BuyoutRecord:
    """Record of a contract buyout."""
    player_name: str
    original_contract: str          # e.g., "$25/N1"
    buyout_salary_cost: int         # amount deducted from salary cap
    buyout_faab_cost: int           # amount deducted from FAAB (if FAAB buyout)
    remaining_years: int            # years of buyout obligation remaining
    use_faab: bool = False          # whether FAAB path was chosen
    note: str = ""                  # e.g., "(Legal issue)"

    @property
    def display(self) -> str:
        """Human-readable buyout string like '$25/N1-13=12'."""
        total = self.buyout_salary_cost + self.buyout_faab_cost
        return f"{self.original_contract}-{self.buyout_faab_cost}={self.buyout_salary_cost}"


@dataclass
class Player:
    """Represents a player on a team roster."""
    name: str
    position: str                   # Yahoo position code(s), e.g., "SP", "LF,CF"
    contract: Contract
    yahoo_player_id: Optional[str] = None
    is_active_keeper: bool = True   # False if bench keeper (R contract)

    @property
    def display(self) -> str:
        return f"{self.position} {self.name} {self.contract.display}"


@dataclass
class Team:
    """Represents a fantasy team."""
    manager_name: str
    team_name: str                  # Yahoo team name, e.g., "Kansas City Royals"
    line_name: str = ""             # LINE display name
    yahoo_team_id: Optional[str] = None

    players: list[Player] = field(default_factory=list)
    buyout_records: list[BuyoutRecord] = field(default_factory=list)

    # Financial info
    salary_cap: int = 0
    faab_budget: int = 0
    ranking_bonus: int = 0
    trade_compensation: int = 0
    previous_rank: Optional[int] = None

    @property
    def active_keepers(self) -> list[Player]:
        """Players with A/B/N/O contracts (count toward 10-man limit)."""
        return [p for p in self.players
                if p.contract.contract_type != ContractType.R
                and p.is_active_keeper]

    @property
    def bench_keepers(self) -> list[Player]:
        """Players with R contracts (bench keepers, max 2)."""
        return [p for p in self.players
                if p.contract.contract_type == ContractType.R]

    @property
    def total_keeper_cost(self) -> int:
        """Sum of all keeper salaries (excluding special clause players)."""
        return sum(
            p.contract.salary for p in self.players
            if not p.contract.is_special_clause_active
        )

    @property
    def total_buyout_cost(self) -> int:
        """Sum of all buyout salary costs."""
        return sum(b.buyout_salary_cost for b in self.buyout_records)

    @property
    def total_buyout_faab_cost(self) -> int:
        """Sum of all buyout FAAB costs."""
        return sum(b.buyout_faab_cost for b in self.buyout_records)

    @property
    def available_salary(self) -> int:
        """Remaining salary cap for draft."""
        return (self.salary_cap + self.ranking_bonus + self.trade_compensation
                - self.total_keeper_cost - self.total_buyout_cost)

    @property
    def available_faab(self) -> int:
        """Remaining FAAB budget."""
        return self.faab_budget - self.total_buyout_faab_cost

    @property
    def special_clause_players(self) -> list[Player]:
        """Players under special clause (no salary, no roster spot)."""
        return [p for p in self.players if p.contract.is_special_clause_active]


@dataclass
class LeagueState:
    """Snapshot of the entire league for a given season."""
    year: int
    teams: list[Team] = field(default_factory=list)

    @property
    def salary_cap(self) -> int:
        from config.settings import get_salary_cap
        return get_salary_cap(self.year)
