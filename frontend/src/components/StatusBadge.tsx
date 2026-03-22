"use client";

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  IL: {
    label: "IL",
    className: "bg-red-100 text-red-700 border-red-200",
  },
  "IL+": {
    label: "IL-60",
    className: "bg-red-200 text-red-800 border-red-300",
  },
  "IL-LT": {
    label: "IL-LT",
    className: "bg-red-200 text-red-800 border-red-300",
  },
  DTD: {
    label: "DTD",
    className: "bg-yellow-100 text-yellow-700 border-yellow-200",
  },
  NA: {
    label: "NA",
    className: "bg-gray-100 text-gray-600 border-gray-200",
  },
  O: {
    label: "O",
    className: "bg-orange-100 text-orange-700 border-orange-200",
  },
  SUSP: {
    label: "SUSP",
    className: "bg-purple-100 text-purple-700 border-purple-200",
  },
};

interface StatusBadgeProps {
  status?: string | null;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  if (!status) return null;

  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className: "bg-gray-100 text-gray-600 border-gray-200",
  };

  return (
    <span
      className={`inline-flex items-center rounded border px-1 py-0.5 text-[10px] font-semibold leading-none ${config.className}`}
      title={status}
    >
      {config.label}
    </span>
  );
}
