"""
Fantasy Baseball Keeper League - Serializers

Converts existing Python dataclass models to Pydantic API schemas.
"""
from __future__ import annotations

from typing import Optional

from src.contract.models import (
    BuyoutRecord,
    Contract,
    ContractType,
    LeagueState,
    Player,
    Team,
)
from api.schemas import (
    BuyoutRecordSchema,
    ContractSchema,
    ContractTransitionSchema,
    LeagueSnapshotSchema,
    PlayerSchema,
    TeamSchema,
)


def serialize_contract(c: Contract) -> ContractSchema:
    return ContractSchema(
        contract_type=c.contract_type.value,
        salary=c.salary,
        extension_years=c.extension_years,
        display=c.display,
        remaining_years=c.remaining_years,
        is_keepable=c.is_keepable,
        special_status=c.special_status.value,
    )


def serialize_buyout(b: BuyoutRecord) -> BuyoutRecordSchema:
    return BuyoutRecordSchema(
        player_name=b.player_name,
        original_contract=b.original_contract,
        buyout_salary_cost=b.buyout_salary_cost,
        buyout_faab_cost=b.buyout_faab_cost,
        remaining_years=b.remaining_years,
        use_faab=b.use_faab,
        note=b.note,
        display=b.display,
    )


def serialize_player(p: Player) -> PlayerSchema:
    return PlayerSchema(
        name=p.name,
        position=p.position,
        contract=serialize_contract(p.contract),
        yahoo_player_id=p.yahoo_player_id,
        is_active_keeper=p.is_active_keeper,
    )


def serialize_team(t: Team, db_team_id: Optional[int] = None) -> TeamSchema:
    return TeamSchema(
        id=db_team_id,
        manager_name=t.manager_name,
        team_name=t.team_name,
        yahoo_team_id=t.yahoo_team_id,
        players=[serialize_player(p) for p in t.players],
        buyout_records=[serialize_buyout(b) for b in t.buyout_records],
        salary_cap=t.salary_cap,
        faab_budget=t.faab_budget,
        ranking_bonus=t.ranking_bonus,
        trade_compensation=t.trade_compensation,
        previous_rank=t.previous_rank,
        total_keeper_cost=t.total_keeper_cost,
        total_buyout_cost=t.total_buyout_cost,
        total_buyout_faab_cost=t.total_buyout_faab_cost,
        available_salary=t.available_salary,
        available_faab=t.available_faab,
        active_keeper_count=len(t.active_keepers),
        bench_keeper_count=len(t.bench_keepers),
    )


def serialize_league_state(ls: LeagueState) -> LeagueSnapshotSchema:
    return LeagueSnapshotSchema(
        year=ls.year,
        salary_cap=ls.salary_cap,
        teams=[serialize_team(t) for t in ls.teams],
    )


def league_state_to_dict(ls: LeagueState) -> dict:
    """Serialize LeagueState to a JSON-safe dict for database storage."""
    return {
        "year": ls.year,
        "teams": [
            {
                "manager_name": t.manager_name,
                "team_name": t.team_name,
                "yahoo_team_id": t.yahoo_team_id,
                "salary_cap": t.salary_cap,
                "faab_budget": t.faab_budget,
                "ranking_bonus": t.ranking_bonus,
                "trade_compensation": t.trade_compensation,
                "previous_rank": t.previous_rank,
                "players": [
                    {
                        "name": p.name,
                        "position": p.position,
                        "contract_type": p.contract.contract_type.value,
                        "salary": p.contract.salary,
                        "extension_years": p.contract.extension_years,
                        "special_status": p.contract.special_status.value,
                        "yahoo_player_id": p.yahoo_player_id,
                        "is_active_keeper": p.is_active_keeper,
                    }
                    for p in t.players
                ],
                "buyout_records": [
                    {
                        "player_name": b.player_name,
                        "original_contract": b.original_contract,
                        "buyout_salary_cost": b.buyout_salary_cost,
                        "buyout_faab_cost": b.buyout_faab_cost,
                        "remaining_years": b.remaining_years,
                        "use_faab": b.use_faab,
                        "note": b.note,
                    }
                    for b in t.buyout_records
                ],
            }
            for t in ls.teams
        ],
    }


def dict_to_league_state(data: dict) -> LeagueState:
    """Deserialize a dict from database storage back to LeagueState."""
    from src.contract.models import SpecialStatus

    teams = []
    for td in data.get("teams", []):
        players = []
        for pd in td.get("players", []):
            ct_map = {v.value: v for v in ContractType}
            ss_map = {v.value: v for v in SpecialStatus}
            contract = Contract(
                contract_type=ct_map.get(pd["contract_type"], ContractType.A),
                salary=pd["salary"],
                extension_years=pd.get("extension_years", 0),
                special_status=ss_map.get(pd.get("special_status", "none"), SpecialStatus.NONE),
            )
            players.append(Player(
                name=pd["name"],
                position=pd.get("position", ""),
                contract=contract,
                yahoo_player_id=pd.get("yahoo_player_id"),
                is_active_keeper=pd.get("is_active_keeper", True),
            ))
        buyouts = []
        for bd in td.get("buyout_records", []):
            buyouts.append(BuyoutRecord(
                player_name=bd["player_name"],
                original_contract=bd["original_contract"],
                buyout_salary_cost=bd["buyout_salary_cost"],
                buyout_faab_cost=bd["buyout_faab_cost"],
                remaining_years=bd.get("remaining_years", 1),
                use_faab=bd.get("use_faab", False),
                note=bd.get("note", ""),
            ))
        team = Team(
            manager_name=td["manager_name"],
            team_name=td.get("team_name", ""),
            yahoo_team_id=td.get("yahoo_team_id"),
            players=players,
            buyout_records=buyouts,
            salary_cap=td.get("salary_cap", 0),
            faab_budget=td.get("faab_budget", 0),
            ranking_bonus=td.get("ranking_bonus", 0),
            trade_compensation=td.get("trade_compensation", 0),
            previous_rank=td.get("previous_rank"),
        )
        teams.append(team)

    return LeagueState(year=data["year"], teams=teams)
