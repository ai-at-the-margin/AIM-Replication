import React from "react";
import { DataTable, Pill, SectionTitle } from "@/components/charts/Primitives";
import { TracingBeam } from "@/components/ui/tracing-beam";
import { useBundle } from "@/lib/data";
import { num, signed } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
function verdict(r: any): { tone: "good" | "warn" | "bad" | "neutral"; text: string } {
  if (r.ours === null || r.ours === undefined) return { tone: "neutral", text: "not measured" };
  const d = Math.abs(r.difference ?? 0);
  if (d < 0.1) return { tone: "good", text: "close" };
  if ((r.paper ?? 0) * r.ours > 0) return { tone: "warn", text: "same sign" };
  return { tone: "bad", text: "different sign" };
}

export function Results() {
  const { analysis, meta } = useBundle();
  const rows: any[] = analysis.paper_comparison ?? [];
  const max = Math.max(1, ...rows.flatMap((r) => [Math.abs(r.paper ?? 0), Math.abs(r.ours ?? 0)]));
  const sections = [
    { title: "Free-form books", keys: ["jaccard_L1", "jaccard_L4", "freeform_size", "freeform_quality", "freeform_momentum", "freeform_value", "lowvol_L1", "lowvol_L4"] },
    { title: "Mandates (search off)", keys: ["value_unconstrained", "value_mandate", "quality_unconstrained", "quality_mandate", "momentum_unconstrained", "momentum_mandate_offline"] },
    { title: "Search", keys: ["momentum_mandate_connected", "momentum_mandate_invoked_lo", "momentum_mandate_invoked_hi", "single_stock_value", "single_stock_unconstrained", "single_stock_quality", "lookup_in_book"] },
    { title: "Refusals", keys: ["refusal_L1", "refusal_other_max"] },
  ];
  return (
    <div>
      <SectionTitle eyebrow="Data" title="Our numbers next to the paper's">
        The paper's headline numbers are sanity checks, not targets (BUILD_BRIEF §1.1). Each difference needs an explanation in docs/RESULTS.md before the numbers circulate. {meta.synthetic && <b>On the demo dataset these comparisons only show the plumbing works.</b>}
      </SectionTitle>
      <TracingBeam className="px-2">
        <div className="space-y-10 pl-4 md:pl-8">
          {sections.map((s) => (
            <section key={s.title}>
              <h2 className="mb-3 text-lg font-semibold text-[var(--ink)]">{s.title}</h2>
              <div className="space-y-2">
                {s.keys.map((k) => rows.find((r) => r.metric === k)).filter(Boolean).map((r: any) => {
                  const v = verdict(r);
                  return (
                    <div key={r.metric} className="grid grid-cols-1 items-center gap-3 rounded-xl border border-black/10 bg-[var(--surface)] p-3 md:grid-cols-[1.3fr_1fr_auto] dark:border-white/10">
                      <div>
                        <div className="text-sm font-medium text-[var(--ink)]">{r.label}</div>
                        {r.note && <div className="text-[11px] text-[var(--muted)]">{r.note}</div>}
                      </div>
                      <div className="space-y-1">
                        {[["paper", r.paper, "var(--axis)"], ["ours", r.ours, "var(--s1)"]].map(([label, val, color]: any) => (
                          <div key={label} className="flex items-center gap-2 text-[11px]">
                            <span className="w-9 text-[var(--ink-2)]">{label}</span>
                            <div className="relative h-2.5 flex-1 rounded-full bg-black/[0.04] dark:bg-white/[0.06]">
                              <div className="absolute top-0 h-2.5 w-px bg-[var(--axis)]" style={{ left: "50%" }} />
                              {val !== null && val !== undefined && (
                                <div className="absolute top-0 h-2.5 rounded-full" style={{ background: color, left: val >= 0 ? "50%" : `${50 - (Math.abs(val) / max) * 50}%`, width: `${(Math.abs(val) / max) * 50}%` }} />
                              )}
                            </div>
                            <span className="tabular w-12 text-right font-semibold">{signed(val)}</span>
                          </div>
                        ))}
                      </div>
                      <div className="text-right"><Pill tone={v.tone}>{v.text}</Pill><div className="tabular mt-1 text-[11px] text-[var(--muted)]">Δ {signed(r.difference)}</div></div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
          <section>
            <h2 className="mb-3 text-lg font-semibold text-[var(--ink)]">All comparisons</h2>
            <DataTable dense rows={rows} columns={[{ key: "label", label: "Metric" }, { key: "paper", label: "Paper", align: "right", render: (r) => num(r.paper) }, { key: "ours", label: "Ours", align: "right", render: (r) => num(r.ours) }, { key: "difference", label: "Δ", align: "right", render: (r) => signed(r.difference) }]} />
          </section>
        </div>
      </TracingBeam>
    </div>
  );
}
