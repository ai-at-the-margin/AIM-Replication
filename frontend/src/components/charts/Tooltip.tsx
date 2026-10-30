import React from "react";

export function TipBox({ title, rows }: { title?: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="pointer-events-none min-w-[150px] rounded-lg border border-black/10 bg-[var(--surface)] px-3 py-2 text-xs shadow-xl dark:border-white/15">
      {title && <div className="mb-1 font-medium text-[var(--ink-2)]">{title}</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-[var(--ink-2)]">
            {r.color && <span className="inline-block h-0.5 w-3 rounded" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="tabular font-semibold text-[var(--ink)]">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

/* Recharts custom tooltip: values lead, labels follow. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function RechartsTip({ active, payload, label, format }: any) {
  if (!active || !payload || payload.length === 0) return null;
  const fmt = format ?? ((v: number) => (typeof v === "number" ? v.toFixed(2) : String(v)));
  return (
    <TipBox
      title={String(label ?? payload[0]?.payload?.label ?? "")}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      rows={payload.map((p: any) => ({ label: String(p.name), value: fmt(p.value, p), color: p.color || p.fill || p.stroke }))}
    />
  );
}

export function useFloatingTip() {
  const [tip, setTip] = React.useState<{ x: number; y: number; node: React.ReactNode } | null>(null);
  const layer = tip ? (
    <div className="pointer-events-none fixed z-50" style={{ left: tip.x + 14, top: tip.y + 14 }}>
      {tip.node}
    </div>
  ) : null;
  return { setTip, layer };
}
