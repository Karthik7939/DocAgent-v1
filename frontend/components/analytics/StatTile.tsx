import { ReactNode } from "react";

export type MetricStatus = "good" | "warning" | "danger" | "neutral";

const STATUS_STYLES: Record<MetricStatus, { icon: string; badge: string }> = {
  good: {
    icon: "bg-emerald-50 text-emerald-600 border-emerald-200",
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  warning: {
    icon: "bg-yellow-50 text-yellow-700 border-yellow-300",
    badge: "bg-yellow-50 text-yellow-800 border-yellow-300",
  },
  danger: {
    icon: "bg-red-50 text-red-600 border-red-200",
    badge: "bg-red-50 text-red-700 border-red-200",
  },
  neutral: {
    icon: "bg-teal/10 text-teal border-teal/20",
    badge: "bg-teal/10 text-teal border-teal/20",
  },
};

interface StatTileProps {
  label: string;
  value: string;
  icon: ReactNode;
  status?: MetricStatus;
  sublabel?: string;
  badge?: string;
}

/** A single headline-number KPI card — see dataviz skill's "stat tile" figure contract. */
export default function StatTile({
  label,
  value,
  icon,
  status = "neutral",
  sublabel,
  badge,
}: StatTileProps) {
  const styles = STATUS_STYLES[status];

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm flex items-start gap-4">
      <div
        className={`flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl border ${styles.icon}`}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted">{label}</p>
          {badge && (
            <span
              className={`shrink-0 inline-flex items-center rounded-full border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${styles.badge}`}
            >
              {badge}
            </span>
          )}
        </div>
        <p className="mt-1 text-2xl font-extrabold text-text leading-none">{value}</p>
        {sublabel && <p className="mt-1.5 text-xs text-muted">{sublabel}</p>}
      </div>
    </div>
  );
}
