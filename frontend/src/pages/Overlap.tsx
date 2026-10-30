import React, { useState } from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { Heatmap } from "@/components/charts/Heatmap";
import { DataTable, Segmented, SectionTitle } from "@/components/charts/Primitives";
import { GroupedBars } from "@/components/charts/RC";
import { useBundle } from "@/lib/data";
import { num, pct, PROMPT_LABEL, sectorName, shortModel } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const GROUPS = [
  { key: "a_flagships", label: "(a) Flagship pair", color: "var(--s1)" },
  { key: "b_cross_provider", label: "(b) All cross-provider pairs", color: "var(--s2)" },
  { key: "c_within_provider", label: "(c) Within provider", color: "var(--s3)" },
  { key: "d_within_model", label: "(d) Within model", color: "var(--s4)" },
];

export function Overlap() {
  const { analysis } = useBundle();
  const [stage, setStage] = useState("A");
  const stageData = analysis.overlap?.[stage] ?? {};
  const prompts = Object.keys(stageData).sort((a, b) => order(a) - order(b));
  const [prompt, setPrompt] = useState("L4");
  const activePrompt = stageData[prompt] ? prompt : prompts[prompts.length - 1] ?? "";
  const active = stageData[activePrompt];
  const rows = prompts.map((p) => {
    const row: any = { prompt: p };
    for (const g of GROUPS) {
      const s = stageData[p]?.[g.key];
      row[g.key] = s?.mean ?? null;
      row[g.key + "_err"] = s && s.lo !== null && s.hi !== null ? [s.mean - s.lo, s.hi - s.mean] : [0, 0];
    }
    return row;
  });
  const consensus = analysis.consensus?.by_stage?.[stage]?.[activePrompt];
  return (
    <div>
      <SectionTitle eyebrow="Figure 1" title="Name overlap">
        Mean Jaccard similarity of issuer sets over pairs of individual repetitions. Share classes, cross-listings and ADRs are collapsed to one issuer first, so GOOGL and GOOG, or TSM and 2330.TW, count as the same name.
      </SectionTitle>
      <div className="mb-5"><Segmented id="ov-stage" value={stage} onChange={setStage} size="md"
        options={[{ value: "A", label: "Stage A · free-form" }, { value: "B", label: "Stage B · mandates" }, { value: "C", label: "Stage C · search" }]} /></div>
      <ChartCard figure="Fig. 1a" title="Name convergence by prompt" subtitle="Bars show four baselines with 95% bootstrap intervals (2,000 draws, resampling repetitions within cells). Paper: 0.69 at L1 falling to 0.38 at L4 for cross-provider flagship pairs."
        table={<DataTable dense rows={rows} columns={[{ key: "prompt", label: "Prompt" }, ...GROUPS.map((g) => ({ key: g.key, label: g.label, align: "right" as const, render: (r: any) => num(r[g.key]) }))]} />}>
        {rows.length ? <GroupedBars data={rows} xKey="prompt" yDomain={[0, 1]} height={320}
          series={GROUPS.map((g) => ({ key: g.key, label: g.label, color: g.color, errKey: g.key + "_err" }))} /> : <Empty text="No valid books for this stage yet." />}
      </ChartCard>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <ChartCard figure="Fig. 1b" title="Model × model overlap" subtitle="Diagonal: within-model self-stability (distinct repetition pairs). Off-diagonal: mean over all cross-model repetition pairs."
          actions={<Segmented id="ov-prompt" value={activePrompt} onChange={setPrompt} options={prompts.map((p) => ({ value: p, label: p }))} />}>
          {active ? <Heatmap rows={active.models} cols={active.models} values={active.heatmap} mode="sequential" max={0.85}
            rowLabel={shortModel} colLabel={(c) => <span className="inline-block max-w-[54px] truncate align-bottom text-[10px]" title={c}>{shortModel(c)}</span>} cellHeight={26} /> : <Empty text="No data." />}
        </ChartCard>
        <ChartCard title="Consensus names" subtitle="A name is a consensus name for a model if it appears in at least half of that model's repetitions (§8.2).">
          {consensus ? (
            <div className="space-y-4">
              <div>
                <div className="mb-1 text-xs font-semibold text-[var(--ink-2)]">In every model's consensus ({consensus.all_model_consensus.length})</div>
                <div className="flex flex-wrap gap-1.5">{consensus.all_model_consensus.map((n: any) => <NameChip key={n.issuer_id} n={n} />)}{consensus.all_model_consensus.length === 0 && <span className="text-xs text-[var(--muted)]">none</span>}</div>
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold text-[var(--ink-2)]">In both flagships' consensus ({consensus.flagship_consensus.length})</div>
                <div className="flex flex-wrap gap-1.5">{consensus.flagship_consensus.map((n: any) => <NameChip key={n.issuer_id} n={n} />)}</div>
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold text-[var(--ink-2)]">Most frequent names across {consensus.n_books} books ({PROMPT_LABEL[activePrompt] ?? activePrompt})</div>
                <div className="space-y-1">
                  {consensus.top_names.slice(0, 12).map((n: any) => (
                    <div key={n.issuer_id} className="flex items-center gap-2 text-xs">
                      <span className="w-40 truncate text-[var(--ink)]" title={n.name}>{n.name}</span>
                      <div className="h-2 flex-1 rounded-full bg-black/[0.05] dark:bg-white/[0.07]"><div className="h-2 rounded-full bg-[var(--s1)]" style={{ width: pct(n.share_of_books) }} /></div>
                      <span className="tabular w-10 text-right text-[var(--ink-2)]">{pct(n.share_of_books)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : <Empty text="No consensus data." />}
        </ChartCard>
      </div>
    </div>
  );
}

function NameChip({ n }: { n: any }) {
  return <span className="rounded-full border border-black/10 px-2 py-0.5 text-[11px] text-[var(--ink)] dark:border-white/15" title={`${sectorName(n.sector)} · ${n.country}`}>{n.name}</span>;
}

function order(p: string) {
  const list = ["L1", "L2", "L3", "L4", "VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"];
  const i = list.indexOf(p);
  return i < 0 ? 99 : i;
}
