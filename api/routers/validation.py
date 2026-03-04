"""
Fantasy Baseball Keeper League - Validation Routes
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.schemas import ValidationResult

router = APIRouter()


class ValidateKeeperListRequest(BaseModel):
    team_id: int
    year: int
    selections: list[dict]  # [{player_name, action, extension_years}]


class BuyoutCalculationRequest(BaseModel):
    player_name: str
    contract_type: str  # "A", "B", "N", "O", "R"
    salary: int
    extension_years: int = 0
    use_faab: bool = False


class BuyoutCalculationResponse(BaseModel):
    player_name: str
    total_cost: int
    salary_cap_cost: int
    faab_cost: int
    remaining_years: int
    use_faab: bool
    yearly_breakdown: list[dict]


@router.post("/keeper-list", response_model=ValidationResult)
async def validate_keeper_list(body: ValidateKeeperListRequest):
    """
    Validate a keeper list without saving.
    Useful for real-time frontend validation against the backend engine.
    """
    from api.routers.teams import _validate_selections

    # Convert selections to DB format
    selections_db = [
        {
            "player_name": s["player_name"],
            "action": s["action"],
            "extension_years": s.get("extension_years", 0),
            "current_contract": s.get("current_contract", ""),
            "next_contract": s.get("next_contract", ""),
        }
        for s in body.selections
    ]

    return _validate_selections(body.year, body.team_id, selections_db)


@router.post("/buyout-calculation", response_model=BuyoutCalculationResponse)
async def calculate_buyout(body: BuyoutCalculationRequest):
    """Calculate buyout cost for a specific player contract."""
    from src.contract.engine import calculate_buyout as _calc_buyout
    from src.contract.models import Contract, ContractType, Player

    ct_map = {v.value: v for v in ContractType}
    contract_type = ct_map.get(body.contract_type)
    if not contract_type:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid contract type: {body.contract_type}")

    contract = Contract(
        contract_type=contract_type,
        salary=body.salary,
        extension_years=body.extension_years,
    )
    player = Player(
        name=body.player_name,
        position="",
        contract=contract,
    )

    result = _calc_buyout(player, use_faab=body.use_faab)

    return BuyoutCalculationResponse(
        player_name=result.player_name,
        total_cost=result.total_cost,
        salary_cap_cost=result.salary_cap_cost,
        faab_cost=result.faab_cost,
        remaining_years=result.remaining_years,
        use_faab=result.use_faab,
        yearly_breakdown=result.yearly_breakdown,
    )
