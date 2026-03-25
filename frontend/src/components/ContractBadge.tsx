import type { ContractType } from "@/types";
import { CONTRACT_BADGE_COLORS } from "@/lib/contract-colors";

interface Props {
  type: ContractType;
  display: string;
}

export default function ContractBadge({ type, display }: Props) {
  const color = CONTRACT_BADGE_COLORS[type] || CONTRACT_BADGE_COLORS.FA;
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${color}`}
    >
      {display}
    </span>
  );
}
