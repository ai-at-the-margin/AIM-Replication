import { motion } from "motion/react";
import React from "react";
import { cn } from "@/lib/utils";

export function Segmented<T extends string>({ options, value, onChange, id, size = "sm" }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; id: string; size?: "sm" | "md";
}) {
  return (
    <div className="no-visible-scrollbar inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-full border border-black/10 bg-black/[0.03] p-1 dark:border-white/10 dark:bg-white/[0.04]">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cn("relative rounded-full px-3 font-medium whitespace-nowrap transition-colors", size === "sm" ? "py-1 text-xs" : "py-1.5 text-sm",
            value === o.value ? "text-white dark:text-black" : "text-[var(--ink-2)] hover:text-[var(--ink)]")}
        >
          {value === o.value && (
            <motion.span layoutId={`seg-${id}`} transition={{ type: "spring", bounce: 0.25, duration: 0.5 }}
              className="absolute inset-0 rounded-full bg-neutral-900 dark:bg-white" />
          )}
          <span className="relative z-10">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

export function StatTile({ label, value, sub, accent, children }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; accent?: string; children?: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col justify-between">
      <div className="text-xs font-medium text-[var(--ink-2)]">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight text-[var(--ink)]" style={accent ? { color: accent } : undefined}>{value}</div>
      {sub && <div className="mt-1 text-xs text-[var(--muted)]">{sub}</div>}
      {children}
    </div>
  );
}

export function Meter({ value, max = 1, color = "var(--s1)", label }: { value: number; max?: number; color?: string; label?: string }) {
  const share = Math.max(0, Math.min(1, value / (max || 1)));
  return (
    <div className="mt-3">
      <div className="h-2 w-full overflow-hidden rounded-full bg-black/[0.06] dark:bg-white/[0.08]" role="meter" aria-valuenow={value} aria-valuemax={max} aria-label={label}>
        <motion.div initial={{ width: 0 }} animate={{ width: `${share * 100}%` }} transition={{ duration: 0.9, ease: "easeOut" }}
          className="h-full rounded-full" style={{ background: color }} />
      </div>
    </div>
  );
}

export function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "info" }) {
  const tones: Record<string, string> = {
    neutral: "border-black/10 text-[var(--ink-2)] dark:border-white/15",
    good: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    bad: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
    info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  };
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", tones[tone])}>{children}</span>;
}

export function DataTable({ columns, rows, dense }: {
  columns: { key: string; label: string; align?: "left" | "right"; render?: (row: any) => React.ReactNode }[]; // eslint-disable-line @typescript-eslint/no-explicit-any
  rows: any[]; // eslint-disable-line @typescript-eslint/no-explicit-any
  dense?: boolean;
}) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="sticky top-0 bg-[var(--surface)]">
        <tr className="border-b border-black/10 dark:border-white/10">
          {columns.map((c) => (
            <th key={c.key} className={cn("px-2 py-2 font-medium text-[var(--ink-2)]", c.align === "right" && "text-right")}>{c.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-black/5 hover:bg-black/[0.02] dark:border-white/5 dark:hover:bg-white/[0.03]">
            {columns.map((c) => (
              <td key={c.key} className={cn("px-2 text-[var(--ink)]", dense ? "py-1" : "py-1.5", c.align === "right" && "tabular text-right")}>
                {c.render ? c.render(r) : String(r[c.key] ?? "–")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LegendRow({ items }: { items: { label: string; color: string; kind?: "rect" | "line" | "dot" }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--ink-2)]">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          {it.kind === "line" ? <span className="inline-block h-0.5 w-4 rounded" style={{ background: it.color }} />
            : it.kind === "dot" ? <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: it.color }} />
            : <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: it.color }} />}
          {it.label}
        </span>
      ))}
    </div>
  );
}

export function SectionTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6">
      {eyebrow && <div className="text-xs font-semibold tracking-[0.18em] text-[var(--s1)] uppercase">{eyebrow}</div>}
      <h1 className="mt-1 bg-gradient-to-b from-neutral-900 to-neutral-600 bg-clip-text text-3xl font-bold tracking-tight text-transparent md:text-4xl dark:from-white dark:to-neutral-400">{title}</h1>
      {children && <div className="mt-2 max-w-4xl text-sm leading-relaxed text-[var(--ink-2)]">{children}</div>}
    </div>
  );
}
