"""
Fantasy Baseball Keeper League - Team & Keeper Selection Routes
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.database import (
    get_all_teams,
    get_keeper_selections,
    get_snapshot,
    get_submission,
    upsert_keeper_selection,
    upsert_submission,
)
from api.dependencies import get_current_user
from api.schemas import (
    KeeperSelectionResponse,
    KeeperSelectionsUpdate,
    KeeperSelectionsWithValidation,
    PlayerKeeperOptionsSchema,
    TeamSchema,
    ValidationResult,
)
from api.serializers import (
    dict_to_league_state,
    serialize_player,
    serialize_team,
)

router = APIRouter()


def _get_team_from_snapshot(year: int, team_id: int):
    """Get a Team model object from a league snapshot by DB team_id."""
    from api.database import get_team_by_id

    db_team = get_team_by_id(team_id)
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")

    snap = get_snapshot(year)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    ls = dict_to_league_state(snap["data"])

    # Find team in snapshot by manager_name
    manager_name = db_team["manager_name"]
    for t in ls.teams:
        if t.manager_name == manager_name:
            return t, db_team

    raise HTTPException(
        status_code=404,
        detail=f"Team '{manager_name}' not found in {year} snapshot",
    )


def _check_team_access(user: dict, team_id: int):
    """Verify user has access to this team (own team or commissioner)."""
    if user.get("is_commissioner"):
        return
    if user.get("team_id") != team_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own team",
        )


@router.get("/", response_model=list[dict])
async def list_teams():
    """List all registered teams."""
    return get_all_teams()


@router.get("/{team_id}/roster/{year}", response_model=TeamSchema)
async def get_team_roster(team_id: int, year: int):
    """Get a team's roster for a specific year."""
    team, db_team = _get_team_from_snapshot(year, team_id)
    return serialize_team(team, db_team_id=db_team["id"])


@router.get("/{team_id}/keeper-options/{year}")
async def get_keeper_options(team_id: int, year: int):
    """Get all keeper options for each player on a team."""
    from src.contract.engine import ContractTransition, generate_keeper_options

    team, db_team = _get_team_from_snapshot(year, team_id)

    result = []
    for player in team.players:
        options = generate_keeper_options(player)
        option_schemas = []
        for opt in options:
            # Determine keep_action and extension_years from the transition
            keep_action = _infer_keep_action(opt, player)
            ext_years = 0
            if "extend" in keep_action:
                # Extract extension years from action string
                ext_years = _extract_extension_years(opt)
                keep_action = "extend"

            option_schemas.append({
                "player_name": opt.player_name,
                "current_contract": opt.current_contract.display,
                "next_contract": opt.next_contract.display if opt.next_contract else None,
                "action": opt.action,
                "salary_change": opt.salary_change,
                "is_mandatory": opt.is_mandatory,
                "keep_action": keep_action,
                "extension_years": ext_years,
            })

        result.append({
            "player": serialize_player(player).model_dump(),
            "options": option_schemas,
        })

    return result


def _infer_keep_action(transition, player) -> str:
    """Infer the keep_action from a ContractTransition."""
    action_lower = transition.action.lower()
    if "release" in action_lower:
        return "release"
    if "rookie" in action_lower or "bench rookie" in action_lower:
        return "rookie"
    if "activate" in action_lower:
        return "activate"
    if "extension" in action_lower or "extend" in action_lower:
        return "extend"
    if "expires" in action_lower or "fa" in action_lower:
        return "fa"
    if "frozen" in action_lower or "special" in action_lower:
        return "frozen"
    return "keep"


def _extract_extension_years(transition) -> int:
    """Extract extension years from a transition action string."""
    import re
    match = re.search(r"N(\d+)\+O", transition.action)
    if match:
        return int(match.group(1))
    return 0


@router.get("/{team_id}/keeper-selections/{year}", response_model=KeeperSelectionsWithValidation)
async def get_team_keeper_selections(
    team_id: int,
    year: int,
    user: dict = Depends(get_current_user),
):
    """Get saved keeper selections for a team."""
    _check_team_access(user, team_id)

    selections_db = get_keeper_selections(year, team_id)
    selections = [
        KeeperSelectionResponse(
            player_name=s["player_name"],
            current_contract=s["current_contract"],
            action=s["action"],
            extension_years=s["extension_years"],
            next_contract=s["next_contract"],
        )
        for s in selections_db
    ]

    # Run validation
    validation = _validate_selections(year, team_id, selections_db)

    # Check submission status
    submission = get_submission(year, team_id)
    is_submitted = submission is not None

    return KeeperSelectionsWithValidation(
        selections=selections,
        validation=validation,
        is_submitted=is_submitted,
    )


@router.put("/{team_id}/keeper-selections/{year}", response_model=KeeperSelectionsWithValidation)
async def update_keeper_selections(
    team_id: int,
    year: int,
    body: KeeperSelectionsUpdate,
    user: dict = Depends(get_current_user),
):
    """Update keeper selections for a team. Returns updated selections with validation."""
    _check_team_access(user, team_id)

    # Check if already submitted
    submission = get_submission(year, team_id)
    if submission and not user.get("is_commissioner"):
        raise HTTPException(
            status_code=400,
            detail="Keeper list already submitted. Contact commissioner to unlock.",
        )

    # Get team data for computing next contracts
    team, db_team = _get_team_from_snapshot(year, team_id)

    # Save each selection
    for sel in body.selections:
        # Compute next contract
        next_contract = _compute_next_contract(team, sel.player_name, sel.action, sel.extension_years)

        # Find current contract
        current_contract = ""
        for p in team.players:
            if p.name == sel.player_name:
                current_contract = p.contract.display
                break

        upsert_keeper_selection(
            year=year,
            team_id=team_id,
            player_name=sel.player_name,
            current_contract=current_contract,
            action=sel.action,
            extension_years=sel.extension_years,
            next_contract=next_contract,
        )

    # Return updated state
    selections_db = get_keeper_selections(year, team_id)
    selections = [
        KeeperSelectionResponse(
            player_name=s["player_name"],
            current_contract=s["current_contract"],
            action=s["action"],
            extension_years=s["extension_years"],
            next_contract=s["next_contract"],
        )
        for s in selections_db
    ]

    validation = _validate_selections(year, team_id, selections_db)

    return KeeperSelectionsWithValidation(
        selections=selections,
        validation=validation,
        is_submitted=False,
    )


@router.post("/{team_id}/keeper-submit/{year}")
async def submit_keeper_list(
    team_id: int,
    year: int,
    user: dict = Depends(get_current_user),
):
    """Submit the final keeper list. Requires all validations to pass."""
    _check_team_access(user, team_id)

    selections_db = get_keeper_selections(year, team_id)
    if not selections_db:
        raise HTTPException(status_code=400, detail="No keeper selections to submit")

    validation = _validate_selections(year, team_id, selections_db)
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed",
                "errors": validation.errors,
            },
        )

    # Save submission
    upsert_submission(
        year=year,
        team_id=team_id,
        submitted_by=user["id"],
        selections=[
            {
                "player_name": s["player_name"],
                "current_contract": s["current_contract"],
                "action": s["action"],
                "extension_years": s["extension_years"],
                "next_contract": s["next_contract"],
            }
            for s in selections_db
        ],
        validation_result=validation.model_dump(),
        is_valid=True,
    )

    return {"message": "Keeper list submitted successfully", "year": year, "team_id": team_id}


def _compute_next_contract(team, player_name: str, action: str, extension_years: int) -> str:
    """Compute the next contract display string for a given action."""
    from src.contract.engine import evaluate_next_contract

    for p in team.players:
        if p.name == player_name:
            transition = evaluate_next_contract(p, keep_action=action, extension_years=extension_years)
            if transition.next_contract:
                return transition.next_contract.display
            return "FA"
    return ""


def _validate_selections(year: int, team_id: int, selections_db: list[dict]) -> ValidationResult:
    """Validate keeper selections against league rules."""
    from config.settings import (
        FAAB_BASE,
        KEEPER_ACTIVE_MAX,
        KEEPER_ACTIVE_MIN,
        KEEPER_BENCH_MAX,
        get_salary_cap,
    )
    from src.contract.engine import evaluate_next_contract
    from api.schemas import FinancialSummary

    try:
        team, db_team = _get_team_from_snapshot(year, team_id)
    except HTTPException:
        return ValidationResult(is_valid=False, errors=["Team or year data not found"])

    errors = []
    warnings = []

    # Build a map of player_name -> selection
    sel_map = {s["player_name"]: s for s in selections_db}

    # Compute keeper costs and counts
    active_count = 0
    bench_count = 0
    keeper_cost = 0

    for p in team.players:
        sel = sel_map.get(p.name)
        if not sel:
            # No selection made for this player -- skip (treat as undecided)
            continue

        action = sel["action"]
        ext_years = sel["extension_years"]

        if action == "release":
            continue

        if action == "fa":
            continue

        # This player is being kept
        transition = evaluate_next_contract(p, keep_action=action, extension_years=ext_years)

        if transition.next_contract is None:
            # Player becomes FA (O contract, etc.)
            if p.contract.contract_type.value == "O":
                errors.append(f"{p.name} has O contract and cannot be kept")
            continue

        next_salary = transition.next_contract.salary
        next_type = transition.next_contract.contract_type.value

        if next_type == "R" and (action == "keep" or action == "rookie"):
            bench_count += 1
            keeper_cost += next_salary
        elif action == "activate":
            # R -> A, counts as active
            active_count += 1
            keeper_cost += next_salary
        else:
            active_count += 1
            keeper_cost += next_salary

    # Validate counts
    if active_count < KEEPER_ACTIVE_MIN:
        # Only warn if some selections are missing (not all players have selections yet)
        total_selections = len(selections_db)
        total_players = len(team.players)
        if total_selections >= total_players:
            errors.append(f"Active keepers too few: {active_count} (minimum {KEEPER_ACTIVE_MIN})")
        else:
            warnings.append(f"Active keepers currently: {active_count} (minimum {KEEPER_ACTIVE_MIN}, selections incomplete)")

    if active_count > KEEPER_ACTIVE_MAX:
        errors.append(f"Active keepers too many: {active_count} (maximum {KEEPER_ACTIVE_MAX})")

    if bench_count > KEEPER_BENCH_MAX:
        errors.append(f"R-contract bench keepers too many: {bench_count} (maximum {KEEPER_BENCH_MAX})")

    # Financial validation
    salary_cap = team.salary_cap or get_salary_cap(year)
    ranking_bonus = team.ranking_bonus
    trade_comp = team.trade_compensation
    buyout_salary_cost = team.total_buyout_cost
    available_salary = salary_cap + ranking_bonus + trade_comp - keeper_cost - buyout_salary_cost

    if available_salary < 0:
        errors.append(
            f"Salary cap exceeded: keeper cost ${keeper_cost} + buyout ${buyout_salary_cost} "
            f"> available ${salary_cap + ranking_bonus + trade_comp}"
        )

    faab_budget = team.faab_budget or FAAB_BASE
    buyout_faab_cost = team.total_buyout_faab_cost
    available_faab = faab_budget - buyout_faab_cost

    if available_faab < 0:
        errors.append(
            f"FAAB budget exceeded: buyout FAAB ${buyout_faab_cost} > budget ${faab_budget}"
        )

    # Warnings
    if available_salary < 20 and available_salary >= 0:
        warnings.append(f"Low remaining salary cap: ${available_salary}")

    financial = FinancialSummary(
        salary_cap=salary_cap,
        ranking_bonus=ranking_bonus,
        trade_compensation=trade_comp,
        keeper_cost=keeper_cost,
        buyout_salary_cost=buyout_salary_cost,
        available_salary=available_salary,
        faab_budget=faab_budget,
        buyout_faab_cost=buyout_faab_cost,
        available_faab=available_faab,
        active_keeper_count=active_count,
        bench_keeper_count=bench_count,
    )

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        financial_summary=financial,
    )
