import type { ContractType } from "@/types";

const COLORS: Record<ContractType, string> = {
  A: "bg-blue-100 text-blue-800",
  B: "bg-green-100 text-green-800",
  N: "bg-orange-100 text-orange-800",
  O: "bg-red-100 text-red-800",
  R: "bg-gray-100 text-gray-800",
  FA: "bg-gray-200 text-gray-500",
};

interface Props {
  type: ContractType;
  display: string;
}

export default function ContractBadge({ type, display }: Props) {
  const color = COLORS[type] || COLORS.FA;
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${color}`}
    >
      {display}
    </span>
  );
}
