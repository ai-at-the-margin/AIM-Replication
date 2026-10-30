import { IconTable, IconChartBar } from "@tabler/icons-react";
import React, { useState } from "react";
import { GlowingEffect } from "@/components/ui/glowing-effect";
import { cn } from "@/lib/utils";

export function ChartCard({
  title, subtitle, children, table, actions, className, footnote, figure,
}: {
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  table?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  footnote?: React.ReactNode;
  figure?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <div className={cn("relative rounded-2xl border border-black/10 p-[1px] dark:border-white/10", className)}>
      <GlowingEffect spread={40} glow disabled={false} proximity={64} inactiveZone={0.01} borderWidth={2} />
      <div className="relative h-full rounded-2xl bg-[var(--surface)] p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {figure && (
                <span className="rounded-full border border-black/10 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-[var(--ink-2)] uppercase dark:border-white/15">
                  {figure}
                </span>
              )}
              <h3 className="text-[15px] font-semibold text-[var(--ink)]">{title}</h3>
            </div>
            {subtitle && <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-[var(--ink-2)]">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2">
            {actions}
            {table && (
              <button
                onClick={() => setShowTable((v) => !v)}
                className="inline-flex items-center gap-1 rounded-lg border border-black/10 px-2 py-1 text-xs text-[var(--ink-2)] transition hover:bg-black/5 dark:border-white/10 dark:hover:bg-white/5"
                aria-label={showTable ? "Show chart" : "Show table"}
              >
                {showTable ? <IconChartBar size={14} /> : <IconTable size={14} />}
                {showTable ? "Chart" : "Table"}
              </button>
            )}
          </div>
        </div>
        {showTable && table ? <div className="max-h-[480px] overflow-auto">{table}</div> : children}
        {footnote && <div className="mt-3 text-[11px] leading-relaxed text-[var(--muted)]">{footnote}</div>}
      </div>
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-black/10 text-sm text-[var(--muted)] dark:border-white/10">
      {text}
    </div>
  );
}
