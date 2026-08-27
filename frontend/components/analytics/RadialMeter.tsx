// Severity ramps use the app's existing status tokens (success/accent-cta/danger),
// not a new palette — see tailwind.config.ts. Track is a lighter step of the
// same ramp per the dataviz skill's Meter contract.
const METER_COLORS = {
  good: { fill: "#1A7A4A", track: "#D7EEE1", text: "text-emerald-700" },
  warning: { fill: "#F2C94C", track: "#FBF1D6", text: "text-yellow-800" },
  danger: { fill: "#C0392B", track: "#F6DAD6", text: "text-red-700" },
} as const;

interface RadialMeterProps {
  label: string;
  /** 0-100 */
  percent: number;
  displayValue: string;
  status: keyof typeof METER_COLORS;
  sublabel?: string;
}

/** A single ratio-against-a-limit figure — see dataviz skill's "Meter" form. */
export default function RadialMeter({
  label,
  percent,
  displayValue,
  status,
  sublabel,
}: RadialMeterProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;
  const colors = METER_COLORS[status];

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm flex items-center gap-5">
      <div className="relative flex-shrink-0" style={{ width: 108, height: 108 }}>
        <svg width="108" height="108" viewBox="0 0 108 108" className="-rotate-90">
          <circle cx="54" cy="54" r={radius} fill="none" stroke={colors.track} strokeWidth="10" />
          <circle
            cx="54"
            cy="54"
            r={radius}
            fill="none"
            stroke={colors.fill}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`text-xl font-extrabold ${colors.text}`}>{displayValue}</span>
        </div>
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wider text-muted">{label}</p>
        {sublabel && <p className="mt-1.5 text-xs text-muted">{sublabel}</p>}
      </div>
    </div>
  );
}
