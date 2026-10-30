import React, { useMemo, useState } from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { Heatmap } from "@/components/charts/Heatmap";
import { DataTable, LegendRow, Segmented, SectionTitle } from "@/components/charts/Primitives";
import { ColoredBars, Lines, Scatterplot, StackedBars } from "@/components/charts/RC";
import { useBundle } from "@/lib/data";
import { CORE_FACTORS, FACTOR_LABEL, num, PROVIDER_COLOR, SERIES, shortModel, signed } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function Factors() {
  const { analysis, meta } = useBundle();
  const ex = analysis.exposures ?? {};
  const byModel: any[] = ex.by_model_stage_a ?? [];
  const models = Array.from(new Set(byModel.map((r) => r.model)));
  const matrix = models.map((m) => CORE_FACTORS.map((f) => byModel.find((r) => r.model === m && r.factor === f)?.mean ?? null));
  const meanRow = CORE_FACTORS.map((_, j) => {
    const vals = matrix.map((r) => r[j]).filter((v) => v !== null) as number[];
    return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
  });
  const mix = ex.sector_mix_stage_a ?? { sectors: [], rows: [] };
  const framing: any[] = ex.by_framing_all ?? [];
  const lineData = ["L1", "L2", "L3", "L4"].map((p) => {
    const row: any = { prompt: p };
    for (const f of ["value", "momentum", "quality", "size", "lowvol"]) row[f] = framing.find((r) => r.prompt_id === p && r.factor === f)?.cross_model_mean ?? null;
    return row;
  });
  const noise: any[] = ex.prompt_effect_vs_noise ?? [];
  const disp: any[] = ex.dispersion_vs_overlap ?? [];
  const space = analysis.factor_space ?? {};
  const [colorBy, setColorBy] = useState<"provider" | "stage">("provider");
  const points: any[] = space.pca?.points ?? [];
  const groups = useMemo(() => {
    if (colorBy === "provider") {
      return ["openai", "anthropic"].map((p) => ({ name: p, color: PROVIDER_COLOR[p], points: points.filter((x) => x.provider === p) }));
    }
    return [["A", "Stage A free-form"], ["B", "Stage B mandates"], ["C", "Stage C search"]].map(([s, label], i) => ({ name: label, color: SERIES[i], points: points.filter((x) => x.stage === s) }));
  }, [points, colorBy]);
  const bins: any[] = space.names_vs_factors?.bins ?? [];
  return (
    <div>
      <SectionTitle eyebrow="Figures 2–3" title="Factor profiles">
        Loadings are in cross-sectional standard deviations against the estimation universe ({meta.universe}), computed from our Barra-style replica: cap-weighted mean zero, equal-weighted unit variance. Low-Vol is minus residual volatility. These are characteristics of the proposed books, not forecasts.
      </SectionTitle>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard figure="Fig. 2a" title="Loadings by model, free-form (Stage A)" subtitle="Paper (six flagships): size +0.55, quality +0.49, momentum −0.31, value −0.06."
          table={<DataTable dense rows={byModel.filter((r) => CORE_FACTORS.includes(r.factor))} columns={[{ key: "model", label: "Model" }, { key: "factor", label: "Factor" }, { key: "mean", label: "Mean", align: "right", render: (r) => signed(r.mean) }, { key: "lo", label: "95% lo", align: "right", render: (r) => signed(r.lo) }, { key: "hi", label: "95% hi", align: "right", render: (r) => signed(r.hi) }, { key: "n", label: "n", align: "right" }]} />}>
          {models.length ? <Heatmap rows={[...models, "mean"]} cols={CORE_FACTORS} values={[...matrix, meanRow]} colLabel={(c) => FACTOR_LABEL[c]} rowLabel={(r) => (r === "mean" ? "mean" : shortModel(r))} format={(v) => signed(v)} highlightLastRow cellHeight={28} /> : <Empty text="No exposures yet." />}
        </ChartCard>
        <ChartCard figure="Fig. 2b" title="Sector mix" subtitle="Average portfolio weight by GICS sector (top eight, rest folded into Other).">
          <StackedBars data={mix.rows} xKey="model" height={360} series={mix.sectors.map((s: string, i: number) => ({ key: s, label: s, color: s === "Other" ? "var(--axis)" : SERIES[i % 8] }))} />
        </ChartCard>
        <ChartCard figure="Fig. 3a" title="How loadings change across framings" subtitle="Cross-model mean loading at each framing (each model weighted equally). Paper: Low-Vol falls from +0.37 at L1 to −0.06 at L4."
          table={<DataTable dense rows={lineData} columns={[{ key: "prompt", label: "Prompt" }, ...["value", "momentum", "quality", "size", "lowvol"].map((f) => ({ key: f, label: FACTOR_LABEL[f], align: "right" as const, render: (r: any) => signed(r[f]) }))]} />}>
          <Lines data={lineData} xKey="prompt" refLine={0} height={300} series={["value", "momentum", "quality", "size", "lowvol"].map((f, i) => ({ key: f, label: FACTOR_LABEL[f], color: SERIES[i] }))} />
        </ChartCard>
        <ChartCard figure="Fig. 3b" title="Framing effect vs run-to-run noise" subtitle="Swing of the cross-model mean across L1–L4, divided by the typical within-cell standard deviation of a single book. Above 1 means the wording moves the factor by more than one book's noise.">
          <ColoredBars layout="horizontal" data={noise.map((r) => ({ factor: FACTOR_LABEL[r.factor], value: r.swing_over_noise, color: "var(--s1)" }))} xKey="factor" yKey="value" colorKey="color" refLine={1} label height={280} />
        </ChartCard>
      </div>
      <h2 className="mt-10 mb-1 text-xl font-semibold">New: different names, similar positions?</h2>
      <p className="mb-4 max-w-4xl text-sm text-[var(--ink-2)]">The paper's central claim, tested directly. Each point in the map is one portfolio projected onto the first two principal components of its six factor loadings. The right panel compares, for pairs of books from different models answering the same prompt, how different their names are with how different their factor positions are.</p>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="Every book in factor space" subtitle={`PCA of loadings; PC1 explains ${num((space.pca?.explained?.[0] ?? 0) * 100, 0)}% and PC2 ${num((space.pca?.explained?.[1] ?? 0) * 100, 0)}% of the variance.`}
          actions={<Segmented id="pca-color" value={colorBy} onChange={setColorBy} options={[{ value: "provider", label: "Provider" }, { value: "stage", label: "Stage" }]} />}>
          {points.length ? <Scatterplot groups={groups} xKey="pc1" yKey="pc2" xLabel="PC1" yLabel="PC2" height={360}
            tip={(p) => [{ label: "model", value: p.model }, { label: "prompt", value: p.prompt_id }, { label: "searched", value: p.searched ? "yes" : "no" }]} /> : <Empty text="No exposures yet." />}
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--ink-2)]">
            {(space.pca?.loadings ?? []).map((l: any) => (
              <span key={l.component}>{l.component}: {CORE_FACTORS.map((f) => `${FACTOR_LABEL[f]} ${signed(l[f], 2)}`).join(" · ")}</span>
            ))}
          </div>
        </ChartCard>
        <ChartCard title="Name distance vs factor distance" subtitle={`Pairs of Stage A books from different models, same prompt. Correlation ${num(space.names_vs_factors?.corr)}; a flat line means books sharing few names still hold similar positions.`}>
          {bins.length ? <Lines data={bins.map((b) => ({ x: Number(((b.lo + b.hi) / 2).toFixed(2)), mean: b.mean_factor_distance, p25: b.p25, p75: b.p75 }))} xKey="x" xType="number" height={300}
            xLabel="name distance (1 − Jaccard)" yLabel="factor distance (sd)"
            series={[{ key: "mean", label: "Mean factor distance", color: "var(--s1)" }, { key: "p25", label: "25th pct", color: "var(--axis)" }, { key: "p75", label: "75th pct", color: "var(--axis)" }]} /> : <Empty text="Not enough pairs." />}
        </ChartCard>
      </div>
      <div className="mt-6">
        <ChartCard title="Dispersion of positions vs dispersion of names" subtitle="Per framing: cross-model standard deviation of mean loadings next to 1 − mean cross-model Jaccard (§8.3).">
          <DataTable dense rows={disp} columns={[{ key: "prompt_id", label: "Prompt" }, { key: "one_minus_jaccard", label: "1 − J̄ (cross-provider)", align: "right", render: (r) => num(r.one_minus_jaccard) },
            ...CORE_FACTORS.map((f) => ({ key: "sd_" + f, label: `sd ${FACTOR_LABEL[f]}`, align: "right" as const, render: (r: any) => num(r["sd_" + f]) }))]} />
          <div className="mt-3"><LegendRow items={[{ label: "Low sd with high 1 − J̄ = different names, similar positions", color: "var(--s1)" }]} /></div>
        </ChartCard>
      </div>
    </div>
  );
}
