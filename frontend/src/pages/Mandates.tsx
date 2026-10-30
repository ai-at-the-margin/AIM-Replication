import React, { useState } from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { Heatmap } from "@/components/charts/Heatmap";
import { DataTable, Segmented, SectionTitle } from "@/components/charts/Primitives";
import { GroupedBars, Lines, Scatterplot } from "@/components/charts/RC";
import { useBundle } from "@/lib/data";
import { FACTOR_LABEL, num, pct, SERIES, shortModel, signed } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const MANDATES = ["VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"];
const FACTORS = ["value", "momentum", "quality", "size", "lowvol"];
const TARGET: Record<string, string> = { VALUE: "value", QUALITY: "quality", MOMENTUM: "momentum" };

export function Mandates() {
  const { analysis } = useBundle();
  const m = analysis.mandates ?? {};
  const [pool, setPool] = useState<"all" | "flagships">("all");
  const heat: any[] = (pool === "all" ? m.heatmap_all : m.heatmap_flagships)?.rows ?? [];
  const matrix = MANDATES.map((md) => FACTORS.map((f) => heat.find((r) => r.mandate === md)?.[f] ?? null));
  const boxed = new Set<string>(Object.entries(TARGET).map(([md, f]) => `${md}|${f}`));
  const deltas: any[] = m.deltas ?? [];
  const models = Array.from(new Set(deltas.map((d) => d.model)));
  const deltaRows = models.map((model) => {
    const row: any = { model: shortModel(model) };
    for (const md of ["VALUE", "QUALITY", "MOMENTUM"]) {
      const d = deltas.find((x) => x.model === model && x.mandate === md);
      row[md] = d?.delta ?? null;
      row[md + "_err"] = d && d.lo !== null ? [d.delta - d.lo, d.hi - d.delta] : [0, 0];
    }
    return row;
  });
  const comp = analysis.compliance ?? {};
  const compRows: any[] = comp.rows ?? [];
  const compModels = Array.from(new Set(compRows.map((r) => r.model)));
  const [state, setState] = useState("offline");
  const compMatrix = compModels.map((model) => MANDATES.map((md) => compRows.find((r) => r.model === model && r.mandate === md && r.search_state === state)?.pass_all ?? null));
  const funnel: any[] = comp.funnel ?? [];
  const steps = funnel[0]?.steps?.map((s: any) => s.step) ?? [];
  const funnelData = steps.map((step: string, i: number) => {
    const row: any = { step };
    for (const f of funnel) row[f.mandate] = f.steps[i]?.share ?? null;
    return row;
  });
  const reasoning: any[] = analysis.reasoning?.rows ?? [];
  const [rMandate, setRMandate] = useState("MOMENTUM");
  const rRow = reasoning.find((r) => r.mandate === rMandate);
  const overlapRows: any[] = m.book_overlap ?? [];
  const overlapMatrix = MANDATES.map((a) => MANDATES.map((b) => overlapRows.find((r) => r.mandate_a === a && r.mandate_b === b)?.jaccard ?? null));
  return (
    <div>
      <SectionTitle eyebrow="Figure 4" title="Mandates">
        Four 300–400-word institutional mandates (Value, Quality, Momentum, Unconstrained), search off. A mandate "works" if it moves the requested factor relative to the same model's Unconstrained book.
      </SectionTitle>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard figure="Fig. 4a" title="Mean loading per mandate × factor" subtitle="Outlined cells are the factor each mandate targets. Paper: Value +0.77 (from −0.12), Quality +0.63 (from +0.67), Momentum −0.38 offline."
          actions={<Segmented id="md-pool" value={pool} onChange={setPool} options={[{ value: "all", label: "All models" }, { value: "flagships", label: "Flagships" }]} />}>
          {heat.length ? <Heatmap rows={MANDATES} cols={FACTORS} values={matrix} boxed={boxed} colLabel={(c) => FACTOR_LABEL[c]} rowLabel={(r) => r[0] + r.slice(1).toLowerCase()} format={(v) => signed(v)} cellHeight={44} /> : <Empty text="Stage B not collected yet." />}
        </ChartCard>
        <ChartCard figure="Fig. 4b" title="Directed response: Δ target vs own Unconstrained" subtitle="95% bootstrap intervals; permutation p-values in the table."
          table={<DataTable dense rows={deltas} columns={[{ key: "model", label: "Model" }, { key: "mandate", label: "Mandate" }, { key: "delta", label: "Δ", align: "right", render: (r) => signed(r.delta) }, { key: "lo", label: "lo", align: "right", render: (r) => signed(r.lo) }, { key: "hi", label: "hi", align: "right", render: (r) => signed(r.hi) }, { key: "p_perm", label: "p", align: "right", render: (r) => num(r.p_perm, 3) }]} />}>
          <GroupedBars data={deltaRows} xKey="model" refLine={0} height={330} barSize={12}
            series={[{ key: "VALUE", label: "Value Δ", color: SERIES[0], errKey: "VALUE_err" }, { key: "QUALITY", label: "Quality Δ", color: SERIES[1], errKey: "QUALITY_err" }, { key: "MOMENTUM", label: "Momentum Δ", color: SERIES[2], errKey: "MOMENTUM_err" }]} />
        </ChartCard>
      </div>
      <h2 className="mt-10 mb-1 text-xl font-semibold">Mandate compliance</h2>
      <p className="mb-4 max-w-4xl text-sm text-[var(--ink-2)]">A book passes if its target exposure exceeds +0.25σ, no weight exceeds 15%, it spans at least four GICS sectors and every holding is at least $5bn (§8.11). A fluent explanation is not evidence of compliance; these tests are.</p>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="Pass rate by model and mandate" actions={<Segmented id="cmp-state" value={state} onChange={setState} options={[{ value: "offline", label: "Offline" }, { value: "connected_invoked", label: "Searched" }, { value: "connected_not_invoked", label: "Search unused" }]} />}>
          {compModels.length ? <Heatmap rows={compModels} cols={MANDATES} values={compMatrix} mode="sequential" max={1} rowLabel={shortModel} colLabel={(c) => c[0] + c.slice(1).toLowerCase()} format={(v) => pct(v)} cellHeight={28} /> : <Empty text="No mandate books yet." />}
        </ChartCard>
        <ChartCard title="Compliance funnel (new)" subtitle="Share of books still passing after each criterion is applied in turn.">
          <Lines data={funnelData} xKey="step" height={300} yFormat={(v) => pct(v)} series={funnel.map((f, i) => ({ key: f.mandate, label: f.mandate[0] + f.mandate.slice(1).toLowerCase(), color: SERIES[i] }))} />
        </ChartCard>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <ChartCard title="Reasoning vs delivery" subtitle={rRow?.coef_words_per_100 !== undefined ? `OLS (HC1): +100 reasoning words → ${signed(rRow.coef_words_per_100)} (se ${num(rRow.se_words)}); mentioning the constraint → ${signed(rRow.coef_mentions)} (se ${num(rRow.se_mentions)}). ${pct(rRow.share_mentioning)} of books mention it.` : "Delivered target exposure against the length of the model's reasoning (§8.10)."}
          actions={<Segmented id="rs-md" value={rMandate} onChange={setRMandate} options={["VALUE", "QUALITY", "MOMENTUM"].map((x) => ({ value: x, label: x[0] + x.slice(1).toLowerCase() }))} />}>
          {rRow?.points ? <Scatterplot height={300} xKey="words" yKey="exposure" xLabel="reasoning words" yLabel={`${FACTOR_LABEL[TARGET[rMandate]]} loading`}
            groups={[{ name: "mentions the constraint", color: "var(--s1)", points: rRow.points.filter((p: any) => p.mentions) }, { name: "does not", color: "var(--s2)", points: rRow.points.filter((p: any) => !p.mentions) }]}
            tip={(p) => [{ label: "words", value: String(Math.round(p.words)) }, { label: "loading", value: signed(p.exposure) }]} /> : <Empty text={rRow?.note ?? "Not enough reasoning text."} />}
        </ChartCard>
        <ChartCard title="Overlap between mandate books" subtitle="Mean Jaccard between books from the same model under different mandates; the diagonal is within-mandate stability.">
          <Heatmap rows={MANDATES} cols={MANDATES} values={overlapMatrix} mode="sequential" max={0.8} rowLabel={(r) => r[0] + r.slice(1).toLowerCase()} colLabel={(c) => c[0] + c.slice(1).toLowerCase()} cellHeight={40} />
        </ChartCard>
      </div>
    </div>
  );
}
