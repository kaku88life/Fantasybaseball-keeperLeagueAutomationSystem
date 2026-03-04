"""
Fantasy Baseball Keeper League - Keeper Decision Report Generator

Generates per-team keeper analysis reports with:
  - Current roster with contract status
  - Next year contract projections
  - Buyout cost calculations (both normal and FAAB paths)
  - Salary cap impact analysis
  - Keeper recommendations
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.settings import FAAB_BASE, KEEPER_ACTIVE_MAX, KEEPER_BENCH_MAX, get_salary_cap
from src.contract.engine import (
    BuyoutCalculation,
    calculate_buyout,
    evaluate_next_contract,
    generate_keeper_options,
    validate_keeper_list,
)
from src.contract.models import ContractType, Player, Team


def generate_team_report(team: Team, target_year: int) -> str:
    """
    Generate a comprehensive keeper decision report for one team.

    Args:
        team: Team object with current roster
        target_year: The year they're making keeper decisions FOR

    Returns:
        Formatted report string
    """
    lines = []
    cap = get_salary_cap(target_year)

    lines.append("=" * 70)
    lines.append(f"Keeper Decision Report - {target_year} Season")
    lines.append(f"Team: {team.team_name}")
    lines.append(f"Manager: {team.manager_name}")
    lines.append("=" * 70)

    # ---- Financial Overview ----
    lines.append(f"\n{'--- Financial Overview ---':^70}")
    lines.append(f"  Salary Cap ({target_year}):     ${cap}")
    lines.append(f"  Ranking Bonus:          ${team.ranking_bonus}")
    lines.append(f"  Trade Compensation:     ${team.trade_compensation}")
    lines.append(f"  Total Available:        ${cap + team.ranking_bonus + team.trade_compensation}")
    lines.append(f"  Current Keeper Cost:    ${team.total_keeper_cost}")
    lines.append(f"  Remaining for Draft:    ${team.available_salary}")
    lines.append(f"  FAAB Budget:            ${team.faab_budget}")
    lines.append(f"  FAAB Buyout Cost:       ${team.total_buyout_faab_cost}")
    lines.append(f"  FAAB Available:         ${team.available_faab}")

    # ---- Current Roster ----
    lines.append(f"\n{'--- Current Roster ---':^70}")
    lines.append(f"  {'Position':<8} {'Player':<28} {'Salary':>7} {'Contract':>8} {'Keepable':>8}")
    lines.append(f"  {'-'*8:<8} {'-'*28:<28} {'-'*7:>7} {'-'*8:>8} {'-'*8:>8}")

    # Active keepers first
    for p in sorted(team.active_keepers, key=lambda x: -x.contract.salary):
        keepable = "Yes" if p.contract.is_keepable else "No (FA)"
        special = " *" if p.contract.is_special_clause_active else ""
        lines.append(
            f"  {p.position:<8} {p.name:<28} "
            f"${p.contract.salary:>5} {p.contract.display:>8} "
            f"{keepable:>8}{special}"
        )

    # Bench keepers (R contracts)
    if team.bench_keepers:
        lines.append(f"\n  Bench Keepers (R contracts):")
        for p in team.bench_keepers:
            lines.append(
                f"  {p.position:<8} {p.name:<28} "
                f"${p.contract.salary:>5} {p.contract.display:>8} "
                f"{'Bench':>8}"
            )

    # Special clause players
    if team.special_clause_players:
        lines.append(f"\n  Special Clause Players (no salary/roster impact):")
        for p in team.special_clause_players:
            lines.append(
                f"  {p.position:<8} {p.name:<28} "
                f"{p.contract.display:>14} "
                f"({p.contract.special_status.value})"
            )

    # ---- Keeper Options for Each Player ----
    lines.append(f"\n{'--- Keeper Options ---':^70}")

    for p in team.players:
        if p.contract.is_special_clause_active:
            continue

        options = generate_keeper_options(p)
        lines.append(f"\n  {p.name} (current: {p.contract.display})")

        for i, opt in enumerate(options):
            prefix = "  >>>" if opt.is_mandatory else f"  [{i+1}]"
            if opt.next_contract:
                salary_note = ""
                if opt.salary_change > 0:
                    salary_note = f" (+${opt.salary_change})"
                elif opt.salary_change < 0:
                    salary_note = f" (-${abs(opt.salary_change)})"
                lines.append(
                    f"  {prefix} {opt.action}"
                    f" -> {opt.next_contract.display}{salary_note}"
                )
            else:
                lines.append(f"  {prefix} {opt.action}")

        # Buyout analysis (if contract has remaining years)
        if p.contract.remaining_years > 0 and p.contract.contract_type in (
            ContractType.N, ContractType.O
        ):
            lines.append(f"      Buyout analysis:")

            # Normal buyout
            normal = calculate_buyout(p, use_faab=False)
            lines.append(
                f"        Normal:  ${normal.salary_cap_cost} from salary cap "
                f"({normal.remaining_years} yr x ${p.contract.salary})"
            )

            # FAAB buyout
            faab = calculate_buyout(p, use_faab=True)
            lines.append(
                f"        FAAB:    ${faab.salary_cap_cost} salary + "
                f"${faab.faab_cost} FAAB "
                f"({faab.remaining_years} yr x "
                f"[${faab.yearly_breakdown[0]['salary_cap']}+${faab.yearly_breakdown[0]['faab']}])"
            )

    # ---- Buyout Records ----
    if team.buyout_records:
        lines.append(f"\n{'--- Active Buyout Obligations ---':^70}")
        for b in team.buyout_records:
            faab_note = f", FAAB: ${b.buyout_faab_cost}" if b.use_faab else ""
            note = f" {b.note}" if b.note else ""
            lines.append(
                f"  {b.player_name:<28} {b.original_contract:>10} "
                f"-> Salary: ${b.buyout_salary_cost}{faab_note}{note}"
            )

    # ---- Validation ----
    errors = validate_keeper_list(team)
    if errors:
        lines.append(f"\n{'--- Validation Warnings ---':^70}")
        for err in errors:
            lines.append(f"  WARNING: {err}")

    # ---- Summary ----
    lines.append(f"\n{'--- Summary ---':^70}")
    active_count = len([p for p in team.active_keepers
                        if not p.contract.is_special_clause_active])
    must_keep = [p for p in team.players
                 if p.contract.contract_type == ContractType.N]
    can_keep = [p for p in team.players
                if p.contract.is_keepable
                and p.contract.contract_type != ContractType.N
                and not p.contract.is_special_clause_active]
    will_fa = [p for p in team.players
               if p.contract.contract_type == ContractType.O]

    lines.append(f"  Must keep (N contracts):    {len(must_keep)}")
    lines.append(f"  Can keep (A/B/R):           {len(can_keep)}")
    lines.append(f"  Will become FA (O):         {len(will_fa)}")
    lines.append(f"  Current active keepers:     {active_count}/{KEEPER_ACTIVE_MAX}")
    lines.append(f"  Bench keepers (R):          {len(team.bench_keepers)}/{KEEPER_BENCH_MAX}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def generate_league_summary(teams: list[Team], target_year: int) -> str:
    """Generate a league-wide summary comparing all teams."""
    lines = []
    cap = get_salary_cap(target_year)

    lines.append("=" * 80)
    lines.append(f"League-Wide Keeper Summary - {target_year} Season")
    lines.append(f"Salary Cap: ${cap}  |  FAAB: ${FAAB_BASE}")
    lines.append("=" * 80)

    lines.append(
        f"\n  {'Manager':<18} {'Keepers':>7} {'Cost':>6} "
        f"{'Cap Left':>8} {'FAAB Left':>9} {'Must Keep':>9} {'Will FA':>7}"
    )
    lines.append(f"  {'-'*18} {'-'*7} {'-'*6} {'-'*8} {'-'*9} {'-'*9} {'-'*7}")

    for team in sorted(teams, key=lambda t: t.total_keeper_cost, reverse=True):
        active = len([p for p in team.active_keepers
                      if not p.contract.is_special_clause_active])
        must_keep = len([p for p in team.players
                         if p.contract.contract_type == ContractType.N])
        will_fa = len([p for p in team.players
                       if p.contract.contract_type == ContractType.O])

        lines.append(
            f"  {team.manager_name:<18} {active:>7} "
            f"${team.total_keeper_cost:>4} "
            f"${team.available_salary:>6} "
            f"${team.available_faab:>7} "
            f"{must_keep:>9} {will_fa:>7}"
        )

    lines.append("\n" + "=" * 80)
    return "\n".join(lines)


# ========== CLI Entry Point ==========
if __name__ == "__main__":
    import argparse

    from scripts.import_excel import import_all

    parser = argparse.ArgumentParser(description="Generate keeper decision reports")
    parser.add_argument("filepath", help="Path to the Excel roster file")
    parser.add_argument("--year", type=int, default=2026,
                        help="Target year for keeper decisions (default: 2026)")
    parser.add_argument("--team", help="Generate report for specific manager only")
    parser.add_argument("--summary", action="store_true",
                        help="Generate league-wide summary only")
    parser.add_argument("--output", help="Output directory for report files")
    args = parser.parse_args()

    print(f"Loading data from: {args.filepath}")
    data = import_all(args.filepath)

    # Use the latest yearly roster
    source_year = args.year - 1  # keeper decisions are made based on previous year data
    available_years = sorted(data["yearly_rosters"].keys())
    if source_year not in available_years:
        source_year = available_years[-1] if available_years else None

    if not source_year:
        print("Error: No roster data found in Excel file")
        sys.exit(1)

    teams = data["yearly_rosters"][source_year]
    print(f"\nUsing {source_year} roster data for {args.year} keeper decisions")
    print(f"Found {len(teams)} teams\n")

    if args.summary:
        report = generate_league_summary(teams, args.year)
        print(report)
    elif args.team:
        # Find specific team
        target = [t for t in teams if args.team.lower() in t.manager_name.lower()]
        if not target:
            print(f"Team '{args.team}' not found. Available managers:")
            for t in teams:
                print(f"  - {t.manager_name}")
            sys.exit(1)
        report = generate_team_report(target[0], args.year)
        print(report)
    else:
        # Generate all reports
        for team in teams:
            report = generate_team_report(team, args.year)
            print(report)
            print("\n")

        # Also print league summary
        summary = generate_league_summary(teams, args.year)
        print(summary)

    # Save to files if output directory specified
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        for team in teams:
            report = generate_team_report(team, args.year)
            filename = f"keeper_report_{team.manager_name}_{args.year}.txt"
            (output_dir / filename).write_text(report, encoding="utf-8")
            print(f"Saved: {output_dir / filename}")

        summary = generate_league_summary(teams, args.year)
        summary_file = output_dir / f"league_summary_{args.year}.txt"
        summary_file.write_text(summary, encoding="utf-8")
        print(f"Saved: {summary_file}")
