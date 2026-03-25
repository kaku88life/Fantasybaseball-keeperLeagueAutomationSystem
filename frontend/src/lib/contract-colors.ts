/**
 * Shared contract type badge color definitions.
 *
 * Used by: analytics/page.tsx, ContractBadge.tsx (via import)
 * Colors match the ContractBadge component conventions.
 */
import type { ContractType } from "@/types";

/** Full contract badge colors (aligned with ContractBadge component) */
export const CONTRACT_BADGE_COLORS: Record<ContractType, string> = {
  A: "bg-blue-100 text-blue-800",
  B: "bg-green-100 text-green-800",
  N: "bg-orange-100 text-orange-800",
  O: "bg-red-100 text-red-800",
  R: "bg-gray-100 text-gray-800",
  FA: "bg-gray-200 text-gray-500",
  TBD: "bg-purple-100 text-purple-700",
};

/**
 * Get badge color for a contract type string.
 * Handles N1/N2/N3 variants by matching "N" prefix.
 */
export function contractBadgeColor(ct: string): string {
  if (ct.startsWith("N")) return CONTRACT_BADGE_COLORS.N;
  return CONTRACT_BADGE_COLORS[ct as ContractType] ?? "bg-gray-100 text-gray-600";
}
