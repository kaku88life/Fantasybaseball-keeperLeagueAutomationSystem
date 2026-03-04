"""
Fantasy Baseball Keeper League - Contract Evaluation Engine

Core logic for contract transitions, buyout calculations, and keeper decisions.
Implements the 1+1+X contract system (A-B-O or A-B-N-O).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from config.settings import (
    EXTENSION_COST_PER_YEAR,
    FAAB_KEEPER_THRESHOLD,
    KEEPER_ACTIVE_MAX,
    KEEPER_BENCH_MAX,
    get_salary_cap,
)
from src.contract.models import (
    BuyoutRecord,
    Contract,
    ContractType,
    Player,
    SpecialStatus,
    Team,
)


@dataclass
class ContractTransition:
    """Result of evaluating a player's next contract."""
    player_name: str
    current_contract: Contract
    next_contract: Optional[Contract]  # None if player becomes FA
    action: str                        # human-readable description
    salary_change: int                 # salary difference (positive = increase)
    is_mandatory: bool                 # whether transition is automatic (N->N-1)


@dataclass
class BuyoutCalculation:
    """Result of buyout cost calculation."""
    player_name: str
    contract: Contract
    total_cost: int                    # total buyout cost
    salary_cap_cost: int               # amount from salary cap
    faab_cost: int                     # amount from FAAB (if FAAB buyout)
    remaining_years: int               # years of buyout payments
    use_faab: bool                     # whether FAAB path is used
    yearly_breakdown: list[dict]       # per-year cost breakdown


def evaluate_next_contract(
    player: Player,
    keep_action: str = "keep",
    extension_years: int = 0,
) -> ContractTransition:
    """
    Evaluate what happens to a player's contract next season.

    Args:
        player: The player to evaluate
        keep_action: "keep" (normal keep), "extend" (B->N+O), "release" (don't keep)
        extension_years: N value if extending (e.g., 3 for N3+O = 4 year total)

    Returns:
        ContractTransition with next contract details

    Contract Flow:
        A -> B (salary unchanged)
        B -> O (salary unchanged, 1 year option)
        B -> N(x)+O (salary + N*$5, extended)
        N(x) -> N(x-1) (automatic, salary unchanged)
        N(1) -> O (automatic, salary unchanged)
        O -> FA (cannot keep)
        R -> stays R (bench) or activate -> A (salary unchanged)
    """
    ct = player.contract
    name = player.name

    # Special clause players: contract frozen
    if ct.is_special_clause_active:
        return ContractTransition(
            player_name=name,
            current_contract=ct,
            next_contract=ct,  # stays frozen
            action=f"Special clause active ({ct.special_status.value}), contract frozen",
            salary_change=0,
            is_mandatory=True,
        )

    # O contract -> FA (cannot keep)
    if ct.contract_type == ContractType.O:
        return ContractTransition(
            player_name=name,
            current_contract=ct,
            next_contract=None,
            action="O contract expires -> FA (cannot keep)",
            salary_change=0,
            is_mandatory=True,
        )

    # Release (don't keep) -> needs buyout
    if keep_action == "release":
        return ContractTransition(
            player_name=name,
            current_contract=ct,
            next_contract=None,
            action="Released -> FA (buyout required if applicable)",
            salary_change=0,
            is_mandatory=False,
        )

    # A -> B
    if ct.contract_type == ContractType.A:
        next_ct = Contract(
            contract_type=ContractType.B,
            salary=ct.salary,
        )
        return ContractTransition(
            player_name=name,
            current_contract=ct,
            next_contract=next_ct,
            action="A -> B (salary unchanged)",
            salary_change=0,
            is_mandatory=False,
        )

    # B -> O or B -> N+O (extension)
    if ct.contract_type == ContractType.B:
        if keep_action == "extend" and extension_years > 0:
            new_salary = ct.salary + extension_years * EXTENSION_COST_PER_YEAR
            next_ct = Contract(
                contract_type=ContractType.N,
                salary=new_salary,
                extension_years=extension_years,
            )
            return ContractTransition(
                player_name=name,
                current_contract=ct,
                next_contract=next_ct,
                action=(
                    f"B -> N{extension_years}+O extension "
                    f"(salary ${ct.salary} -> ${new_salary}, "
                    f"+${extension_years * EXTENSION_COST_PER_YEAR})"
                ),
                salary_change=new_salary - ct.salary,
                is_mandatory=False,
            )
        else:
            next_ct = Contract(
                contract_type=ContractType.O,
                salary=ct.salary,
            )
            return ContractTransition(
                player_name=name,
                current_contract=ct,
                next_contract=next_ct,
                action="B -> O (option year, salary unchanged)",
                salary_change=0,
                is_mandatory=False,
            )

    # N(x) -> N(x-1) or N(1) -> O (automatic)
    if ct.contract_type == ContractType.N:
        if ct.extension_years > 1:
            next_ct = Contract(
                contract_type=ContractType.N,
                salary=ct.salary,
                extension_years=ct.extension_years - 1,
            )
            return ContractTransition(
                player_name=name,
                current_contract=ct,
                next_contract=next_ct,
                action=f"N{ct.extension_years} -> N{ct.extension_years - 1} (automatic, salary unchanged)",
                salary_change=0,
                is_mandatory=True,
            )
        else:  # N1 -> O
            next_ct = Contract(
                contract_type=ContractType.O,
                salary=ct.salary,
            )
            return ContractTransition(
                player_name=name,
                current_contract=ct,
                next_contract=next_ct,
                action="N1 -> O (final extension year, salary unchanged)",
                salary_change=0,
                is_mandatory=True,
            )

    # R -> stay R (bench) or activate -> A
    if ct.contract_type == ContractType.R:
        if keep_action == "activate":
            next_ct = Contract(
                contract_type=ContractType.A,
                salary=ct.salary,
            )
            return ContractTransition(
                player_name=name,
                current_contract=ct,
                next_contract=next_ct,
                action="R -> A (activated from bench, salary unchanged)",
                salary_change=0,
                is_mandatory=False,
            )
        else:
            return ContractTransition(
                player_name=name,
                current_contract=ct,
                next_contract=ct,
                action="R -> R (stays on bench as rookie)",
                salary_change=0,
                is_mandatory=False,
            )

    # Fallback (should not reach here)
    return ContractTransition(
        player_name=name,
        current_contract=ct,
        next_contract=None,
        action=f"Unknown contract type: {ct.contract_type}",
        salary_change=0,
        is_mandatory=False,
    )


def calculate_buyout(
    player: Player,
    use_faab: bool = False,
) -> BuyoutCalculation:
    """
    Calculate buyout cost for releasing a player.

    Buyout rules:
    - Normal buyout: pay full salary for each remaining contract year from salary cap
    - FAAB buyout: pay salary/2 from FAAB each year, salary/2 from salary cap
      - If salary is odd, FAAB pays ceil(salary/2) (the larger half)
    - O contract: 1 year remaining
    - N(x) contract: x + 1 years remaining (N years + O year)
    - A/B contract: 1 year, but typically just don't keep (no buyout needed unless mid-season trade)

    Args:
        player: The player to buy out
        use_faab: Whether to use FAAB buyout path

    Returns:
        BuyoutCalculation with cost breakdown
    """
    ct = player.contract
    salary = ct.salary
    remaining = ct.remaining_years

    if remaining <= 0:
        return BuyoutCalculation(
            player_name=player.name,
            contract=ct,
            total_cost=0,
            salary_cap_cost=0,
            faab_cost=0,
            remaining_years=0,
            use_faab=False,
            yearly_breakdown=[],
        )

    yearly_breakdown = []

    if use_faab:
        # FAAB buyout: split salary in half each year
        # Odd salary -> FAAB pays ceil (the larger half)
        faab_per_year = math.ceil(salary / 2)
        salary_per_year = math.floor(salary / 2)

        total_faab = faab_per_year * remaining
        total_salary = salary_per_year * remaining

        for year_idx in range(remaining):
            yearly_breakdown.append({
                "year": year_idx + 1,
                "salary_cap": salary_per_year,
                "faab": faab_per_year,
                "total": salary,
            })

        return BuyoutCalculation(
            player_name=player.name,
            contract=ct,
            total_cost=total_salary + total_faab,
            salary_cap_cost=total_salary,
            faab_cost=total_faab,
            remaining_years=remaining,
            use_faab=True,
            yearly_breakdown=yearly_breakdown,
        )
    else:
        # Normal buyout: full salary from salary cap each year
        total_cost = salary * remaining

        for year_idx in range(remaining):
            yearly_breakdown.append({
                "year": year_idx + 1,
                "salary_cap": salary,
                "faab": 0,
                "total": salary,
            })

        return BuyoutCalculation(
            player_name=player.name,
            contract=ct,
            total_cost=total_cost,
            salary_cap_cost=total_cost,
            faab_cost=0,
            remaining_years=remaining,
            use_faab=False,
            yearly_breakdown=yearly_breakdown,
        )


def resolve_trade_contract(
    original: Contract,
    trade_price: int,
    trade_contract_type: ContractType,
    trade_extension_years: int = 0,
) -> Contract:
    """
    Resolve contract when a player is traded with different contract status.

    Trade contract rules:
    - Salary: use the HIGHER salary between original and trade price
    - Contract: use the LONGER remaining contract
    - Contract priority (longest to shortest): N/O > B > A > R

    Args:
        original: Player's original contract before trade
        trade_price: The FAAB/draft price the new team acquired the player for
        trade_contract_type: Contract type from the trade
        trade_extension_years: Extension years if N contract from trade

    Returns:
        Resolved contract for the player on the new team
    """
    # Determine which salary is higher
    resolved_salary = max(original.salary, trade_price)

    # Determine which contract is longer
    trade_contract = Contract(
        contract_type=trade_contract_type,
        salary=trade_price,
        extension_years=trade_extension_years,
    )

    # Contract length priority: N+O > O > B > A > R
    contract_priority = {
        ContractType.R: 0,
        ContractType.A: 1,
        ContractType.B: 2,
        ContractType.O: 3,
        ContractType.N: 4,  # longest
    }

    orig_priority = contract_priority.get(original.contract_type, 0)
    trade_priority = contract_priority.get(trade_contract_type, 0)

    # Use longer contract type, or compare remaining years if same type
    if orig_priority > trade_priority:
        resolved_type = original.contract_type
        resolved_ext = original.extension_years
    elif trade_priority > orig_priority:
        resolved_type = trade_contract_type
        resolved_ext = trade_extension_years
    else:
        # Same type, compare remaining years
        if original.remaining_years >= trade_contract.remaining_years:
            resolved_type = original.contract_type
            resolved_ext = original.extension_years
        else:
            resolved_type = trade_contract_type
            resolved_ext = trade_extension_years

    return Contract(
        contract_type=resolved_type,
        salary=resolved_salary,
        extension_years=resolved_ext,
    )


def apply_special_clause(player: Player, status: SpecialStatus) -> Player:
    """
    Apply special clause to a player (retirement, legal issues, etc.).

    When active:
    - No salary payment required
    - Doesn't count toward 10-man keeper limit
    - Must be noted below team roster
    - If player returns, original contract resumes or GM can choose buyout
    """
    player.contract.special_status = status
    return player


def remove_special_clause(player: Player) -> Player:
    """
    Remove special clause when player returns to active play.
    Original contract resumes from where it was frozen.
    """
    player.contract.special_status = SpecialStatus.NONE
    return player


def validate_keeper_list(team: Team) -> list[str]:
    """
    Validate a team's keeper list against league rules.

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    active = team.active_keepers
    bench = team.bench_keepers
    special = team.special_clause_players

    # Active keeper count (6-10)
    active_non_special = [p for p in active if not p.contract.is_special_clause_active]
    if len(active_non_special) < 6:
        errors.append(
            f"Active keepers too few: {len(active_non_special)} (minimum 6)"
        )
    if len(active_non_special) > KEEPER_ACTIVE_MAX:
        errors.append(
            f"Active keepers too many: {len(active_non_special)} (maximum {KEEPER_ACTIVE_MAX})"
        )

    # Bench keepers (max 2 R contracts)
    if len(bench) > KEEPER_BENCH_MAX:
        errors.append(
            f"R-contract bench keepers too many: {len(bench)} (maximum {KEEPER_BENCH_MAX})"
        )

    # O contracts cannot be kept
    o_keepers = [p for p in team.players if p.contract.contract_type == ContractType.O]
    for p in o_keepers:
        errors.append(
            f"{p.name} has O contract and cannot be kept (will become FA)"
        )

    # FAAB >= $10 players must be kept
    # (This is checked during season, not at keeper selection)

    # Salary cap check
    from config.settings import FAAB_BASE
    if team.available_salary < 0:
        errors.append(
            f"Salary cap exceeded: keeper cost ${team.total_keeper_cost} "
            f"exceeds available ${team.salary_cap + team.ranking_bonus + team.trade_compensation}"
        )

    if team.available_faab < 0:
        errors.append(
            f"FAAB budget exceeded: buyout FAAB cost ${team.total_buyout_faab_cost} "
            f"exceeds budget ${team.faab_budget}"
        )

    return errors


def generate_keeper_options(player: Player) -> list[ContractTransition]:
    """
    Generate all possible keeper options for a player.

    Returns:
        List of possible ContractTransitions the GM can choose from
    """
    options = []

    ct = player.contract

    # Special clause: only option is to stay frozen
    if ct.is_special_clause_active:
        options.append(evaluate_next_contract(player))
        return options

    # O contract: only option is release (FA)
    if ct.contract_type == ContractType.O:
        options.append(evaluate_next_contract(player))
        return options

    # A contract: keep as B or release
    if ct.contract_type == ContractType.A:
        options.append(evaluate_next_contract(player, keep_action="keep"))
        options.append(evaluate_next_contract(player, keep_action="release"))
        return options

    # B contract: keep as O, extend N+O (various lengths), or release
    if ct.contract_type == ContractType.B:
        # Keep as O (1 year option)
        options.append(evaluate_next_contract(player, keep_action="keep"))
        # Extend N+O (1-5 years of extension)
        for n in range(1, 6):
            options.append(
                evaluate_next_contract(player, keep_action="extend", extension_years=n)
            )
        # Release
        options.append(evaluate_next_contract(player, keep_action="release"))
        return options

    # N contract: automatic transition (mandatory)
    if ct.contract_type == ContractType.N:
        options.append(evaluate_next_contract(player))
        # Can also choose to release (buyout)
        options.append(evaluate_next_contract(player, keep_action="release"))
        return options

    # R contract: stay bench, activate, or release
    if ct.contract_type == ContractType.R:
        options.append(evaluate_next_contract(player, keep_action="keep"))
        options.append(evaluate_next_contract(player, keep_action="activate"))
        options.append(evaluate_next_contract(player, keep_action="release"))
        return options

    return options
