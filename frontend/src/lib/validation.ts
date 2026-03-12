/**
 * Frontend validation for keeper selections.
 * TypeScript port of backend validation rules for instant feedback.
 */

import type { ContractType, FinancialSummary, Player, Team } from "@/types";

// League constants (must match config/settings.py)
const KEEPER_ACTIVE_MIN = 12;
const KEEPER_ACTIVE_MAX = 15;
const KEEPER_BENCH_MAX = 2;
const EXTENSION_COST_PER_YEAR = 5;

export interface Selection {
  action: string;
  extension_years: number;
}

export interface ClientValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  financial_summary: FinancialSummary;
}

/**
 * Calculate FAAB buyout cost for releasing an N-contract player.
 * Mirrors backend calculate_buyout(player, use_faab=True).
 *
 * FAAB buyout: floor(salary/2) from salary cap + ceil(salary/2) from FAAB per year.
 * remaining_years for N contracts = extension_years + 1 (N years + O year).
 *
 * Returns both per-year costs and total costs across all years.
 * Validation should use per-year (only current year deducted from budget).
 */
export function computeBuyoutCost(
  salary: number,
  remainingYears: number,
): {
  salaryPerYear: number;
  faabPerYear: number;
  salaryCost: number;
  faabCost: number;
} {
  if (remainingYears <= 0)
    return { salaryPerYear: 0, faabPerYear: 0, salaryCost: 0, faabCost: 0 };
  const salaryPerYear = Math.floor(salary / 2);
  const faabPerYear = Math.ceil(salary / 2);
  return {
    salaryPerYear,
    faabPerYear,
    salaryCost: salaryPerYear * remainingYears,
    faabCost: faabPerYear * remainingYears,
  };
}

/**
 * Compute the next contract salary for a given player/action.
 */
export function computeNextSalary(
  contractType: ContractType,
  currentSalary: number,
  action: string,
  extensionYears: number,
): number {
  if (action === "release" || action === "release_normal" || action === "fa") return 0;
  if (action === "legal_issue") return 0; // no salary cost

  if (contractType === "B" && action === "extend" && extensionYears > 0) {
    return currentSalary + extensionYears * EXTENSION_COST_PER_YEAR;
  }

  // All other keeps: salary unchanged
  return currentSalary;
}

/**
 * Determine if a player counts as active keeper or farm rookie.
 * Returns "active" | "farm" | "none" (released/FA)
 */
export function getKeeperCategory(
  contractType: ContractType,
  action: string,
): "active" | "farm" | "none" {
  if (action === "release" || action === "release_normal" || action === "fa") return "none";
  if (action === "legal_issue") return "none"; // no roster spot

  // O contract = FA, cannot keep
  if (contractType === "O") return "none";

  // R contract kept as farm rookie ("keep" from manual, "rookie" from backend inference)
  if (contractType === "R" && (action === "keep" || action === "rookie"))
    return "farm";

  // R contract activated = active
  if (contractType === "R" && action === "activate") return "active";

  // All other types kept = active
  return "active";
}

/**
 * Run client-side validation on current selections.
 * Mirrors backend _validate_selections() logic.
 */
export function validateSelections(
  team: Team,
  selections: Record<string, Selection>,
): ClientValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  let activeCount = 0;
  let farmCount = 0;
  let keeperCost = 0;
  let newBuyoutSalaryCost = 0;
  let newBuyoutFaabCost = 0;

  const totalPlayers = team.players.length;
  const totalSelections = Object.keys(selections).length;

  for (const player of team.players) {
    const sel = selections[player.name];
    const ct = player.contract.contract_type as ContractType;

    // No selection made yet: skip (treat as undecided, same as backend)
    if (!sel) {
      continue;
    }

    // Calculate buyout cost for N-contract players being released
    // Only deduct CURRENT YEAR's portion (buyout is paid annually, not all at once)
    if ((sel.action === "release" || sel.action === "release_normal") && ct === "N") {
      if (sel.action === "release_normal") {
        // Normal buyout: full salary from salary cap per year
        newBuyoutSalaryCost += player.contract.salary;
      } else {
        // FAAB buyout: split salary between cap and FAAB per year
        const buyout = computeBuyoutCost(
          player.contract.salary,
          player.contract.remaining_years,
        );
        newBuyoutSalaryCost += buyout.salaryPerYear;
        newBuyoutFaabCost += buyout.faabPerYear;
      }
    }

    const category = getKeeperCategory(ct, sel.action);

    if (category === "none") continue;

    const nextSalary = computeNextSalary(
      ct,
      player.contract.salary,
      sel.action,
      sel.extension_years,
    );

    if (category === "active") {
      activeCount++;
      keeperCost += nextSalary;
    } else if (category === "farm") {
      farmCount++;
      keeperCost += nextSalary;
    }

    // O contract cannot be kept
    if (ct === "O" && sel.action !== "release" && sel.action !== "fa") {
      errors.push(`${player.name} 是 O 約，無法留用（將成為自由球員）`);
    }
  }

  // Validate counts
  if (activeCount < KEEPER_ACTIVE_MIN) {
    if (totalSelections >= totalPlayers) {
      errors.push(
        `留用人數不足: ${activeCount} 人（最少 ${KEEPER_ACTIVE_MIN} 人）`,
      );
    } else {
      warnings.push(
        `目前留用: ${activeCount} 人（最少 ${KEEPER_ACTIVE_MIN} 人，尚未全部選擇）`,
      );
    }
  }

  if (activeCount > KEEPER_ACTIVE_MAX) {
    errors.push(
      `留用人數超標: ${activeCount} 人（最多 ${KEEPER_ACTIVE_MAX} 人）`,
    );
  }

  if (farmCount > KEEPER_BENCH_MAX) {
    errors.push(
      `農場新秀 (R) 超標: ${farmCount} 人（最多 ${KEEPER_BENCH_MAX} 人）`,
    );
  }

  // Financial validation
  // Carryover buyout costs from previous years + new buyouts from keeper decisions
  const salaryCap = team.salary_cap;
  const rankingBonus = team.ranking_bonus;
  const tradeComp = team.trade_compensation;
  const carryoverBuyoutSalary = team.total_buyout_cost;
  const totalBuyoutSalaryCost = carryoverBuyoutSalary + newBuyoutSalaryCost;
  const availableSalary =
    salaryCap + rankingBonus + tradeComp - keeperCost - totalBuyoutSalaryCost;

  if (availableSalary < 0) {
    errors.push(
      `薪資超標: 留用成本 $${keeperCost} + 買斷 $${totalBuyoutSalaryCost} 超過可用額度 $${salaryCap + rankingBonus + tradeComp}`,
    );
  }

  const faabBudget = team.faab_budget;
  const carryoverBuyoutFaab = team.total_buyout_faab_cost;
  const totalBuyoutFaabCost = carryoverBuyoutFaab + newBuyoutFaabCost;
  const availableFaab = faabBudget - totalBuyoutFaabCost;

  if (availableFaab < 0) {
    errors.push(
      `FAAB 超標: 買斷 FAAB $${totalBuyoutFaabCost} 超過預算 $${faabBudget}`,
    );
  }

  if (availableSalary >= 0 && availableSalary < 20) {
    warnings.push(`剩餘薪資空間偏低: $${availableSalary}`);
  }

  const financialSummary: FinancialSummary = {
    salary_cap: salaryCap,
    ranking_bonus: rankingBonus,
    trade_compensation: tradeComp,
    keeper_cost: keeperCost,
    buyout_salary_cost: totalBuyoutSalaryCost,
    available_salary: availableSalary,
    faab_budget: faabBudget,
    faab_adjustment: 0,
    buyout_faab_cost: totalBuyoutFaabCost,
    available_faab: availableFaab,
    active_keeper_count: activeCount,
    farm_rookie_count: farmCount,
  };

  return {
    is_valid: errors.length === 0,
    errors,
    warnings,
    financial_summary: financialSummary,
  };
}

/**
 * Get human-readable Chinese action label for a keeper option.
 * All domain terms include English alongside Traditional Chinese.
 */
export function getActionLabel(
  contractType: ContractType,
  keepAction: string,
  extensionYears: number,
  currentSalary: number,
): string {
  // FA (O contract auto-release)
  if (keepAction === "fa") {
    return "自由球員 Free Agent";
  }

  // Release / Buyout label depends on contract type
  if (keepAction === "release") {
    if (contractType === "N") {
      return "買斷 FAAB Buyout → FA";
    }
    return "不保留 Release → FA";
  }
  if (keepAction === "release_normal") {
    return "買斷 Buyout (全薪資帽) → FA";
  }

  switch (contractType) {
    case "A":
      if (keepAction === "keep") return "留用 Keep → B 約 (薪資 Salary 不變)";
      break;
    case "B":
      if (keepAction === "keep")
        return "留用 Keep → O 約 (薪資 Salary 不變，最後一年 Final Year)";
      if (keepAction === "extend" && extensionYears > 0) {
        const newSalary =
          currentSalary + extensionYears * EXTENSION_COST_PER_YEAR;
        return `延長 Extend ${extensionYears} 年 → N${extensionYears}+O ($${currentSalary}→$${newSalary})`;
      }
      break;
    case "N":
      if (keepAction === "keep" || keepAction === "frozen") {
        return "自動延續 Auto-renew (薪資 Salary 不變)";
      }
      if (keepAction === "legal_issue") {
        return "法律問題 Legal Issue (合約凍結，不佔薪資/名額)";
      }
      break;
    case "O":
      return "自由球員 Free Agent";
    case "R":
      if (keepAction === "keep" || keepAction === "rookie")
        return "維持農場新秀 Keep as Rookie (R 約)";
      if (keepAction === "activate")
        return "啟用 Activate → A 約 (進入正規合約 Regular Contract)";
      break;
  }

  return keepAction;
}

/**
 * Get the next contract display string for a given action.
 */
export function getNextContractDisplay(
  contractType: ContractType,
  currentSalary: number,
  action: string,
  extensionYears: number,
): string | null {
  if (action === "release" || action === "release_normal") return "FA";
  if (action === "fa") return "FA";
  if (action === "legal_issue") return "凍結 Frozen";

  switch (contractType) {
    case "A":
      if (action === "keep") return `$${currentSalary}/B`;
      break;
    case "B":
      if (action === "keep") return `$${currentSalary}/O`;
      if (action === "extend" && extensionYears > 0) {
        const newSalary =
          currentSalary + extensionYears * EXTENSION_COST_PER_YEAR;
        return `$${newSalary}/N${extensionYears}`;
      }
      break;
    case "N":
      // Automatic transition is handled by the server
      return null;
    case "O":
      return "FA";
    case "R":
      if (action === "keep" || action === "rookie")
        return `$${currentSalary}/R`;
      if (action === "activate") return `$${currentSalary}/A`;
      break;
  }

  return null;
}
