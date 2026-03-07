/**
 * Frontend validation for keeper selections.
 * TypeScript port of backend validation rules for instant feedback.
 */

import type { ContractType, FinancialSummary, Player, Team } from "@/types";

// League constants (must match config/settings.py)
const KEEPER_ACTIVE_MIN = 6;
const KEEPER_ACTIVE_MAX = 10;
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
 * Compute the next contract salary for a given player/action.
 */
export function computeNextSalary(
  contractType: ContractType,
  currentSalary: number,
  action: string,
  extensionYears: number,
): number {
  if (action === "release" || action === "fa") return 0;

  if (contractType === "B" && action === "extend" && extensionYears > 0) {
    return currentSalary + extensionYears * EXTENSION_COST_PER_YEAR;
  }

  // All other keeps: salary unchanged
  return currentSalary;
}

/**
 * Determine if a player counts as active or bench keeper.
 * Returns "active" | "bench" | "none" (released/FA)
 */
export function getKeeperCategory(
  contractType: ContractType,
  action: string,
): "active" | "bench" | "none" {
  if (action === "release" || action === "fa") return "none";

  // O contract = FA, cannot keep
  if (contractType === "O") return "none";

  // A contract designated as rookie -> bench
  if (contractType === "A" && action === "rookie") return "bench";

  // R contract kept on bench
  if (contractType === "R" && action === "keep") return "bench";

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
  let benchCount = 0;
  let keeperCost = 0;

  const totalPlayers = team.players.length;
  const totalSelections = Object.keys(selections).length;

  for (const player of team.players) {
    const sel = selections[player.name];
    if (!sel) continue;

    const ct = player.contract.contract_type as ContractType;
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
    } else if (category === "bench") {
      benchCount++;
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
        `活躍留用人數不足: ${activeCount} 人（最少 ${KEEPER_ACTIVE_MIN} 人）`,
      );
    } else {
      warnings.push(
        `目前活躍留用: ${activeCount} 人（最少 ${KEEPER_ACTIVE_MIN} 人，尚未全部選擇）`,
      );
    }
  }

  if (activeCount > KEEPER_ACTIVE_MAX) {
    errors.push(
      `活躍留用人數超標: ${activeCount} 人（最多 ${KEEPER_ACTIVE_MAX} 人）`,
    );
  }

  if (benchCount > KEEPER_BENCH_MAX) {
    errors.push(
      `板凳新秀 (R) 超標: ${benchCount} 人（最多 ${KEEPER_BENCH_MAX} 人）`,
    );
  }

  // Financial validation
  const salaryCap = team.salary_cap;
  const rankingBonus = team.ranking_bonus;
  const tradeComp = team.trade_compensation;
  const buyoutSalaryCost = team.total_buyout_cost;
  const availableSalary =
    salaryCap + rankingBonus + tradeComp - keeperCost - buyoutSalaryCost;

  if (availableSalary < 0) {
    errors.push(
      `薪資超標: 留用成本 $${keeperCost} + 買斷 $${buyoutSalaryCost} 超過可用額度 $${salaryCap + rankingBonus + tradeComp}`,
    );
  }

  const faabBudget = team.faab_budget;
  const buyoutFaabCost = team.total_buyout_faab_cost;
  const availableFaab = faabBudget - buyoutFaabCost;

  if (availableFaab < 0) {
    errors.push(
      `FAAB 超標: 買斷 FAAB $${buyoutFaabCost} 超過預算 $${faabBudget}`,
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
    buyout_salary_cost: buyoutSalaryCost,
    available_salary: availableSalary,
    faab_budget: faabBudget,
    buyout_faab_cost: buyoutFaabCost,
    available_faab: availableFaab,
    active_keeper_count: activeCount,
    bench_keeper_count: benchCount,
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
 */
export function getActionLabel(
  contractType: ContractType,
  keepAction: string,
  extensionYears: number,
  currentSalary: number,
): string {
  if (keepAction === "release") return "释出 (Release)";

  switch (contractType) {
    case "A":
      if (keepAction === "keep") return "留用 → B 約 (薪資不變)";
      if (keepAction === "rookie") return "指定為 R 約 (板凳新秀)";
      break;
    case "B":
      if (keepAction === "keep") return "留用 → O 約 (薪資不變，最後一年)";
      if (keepAction === "extend" && extensionYears > 0) {
        const newSalary =
          currentSalary + extensionYears * EXTENSION_COST_PER_YEAR;
        return `延長 ${extensionYears} 年 → N${extensionYears}+O ($${currentSalary}→$${newSalary})`;
      }
      break;
    case "N":
      if (keepAction === "keep" || keepAction === "frozen") {
        return "自動延續 (薪資不變)";
      }
      break;
    case "O":
      return "O 約到期 → 自由球員";
    case "R":
      if (keepAction === "keep") return "板凳留用 (保持 R 約)";
      if (keepAction === "activate") return "啟用 → A 約 (進入正規合約)";
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
  if (action === "release") return "FA";
  if (action === "fa") return "FA";

  switch (contractType) {
    case "A":
      if (action === "keep") return `$${currentSalary}/B`;
      if (action === "rookie") return `$${currentSalary}/R`;
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
      if (action === "keep") return `$${currentSalary}/R`;
      if (action === "activate") return `$${currentSalary}/A`;
      break;
  }

  return null;
}
