import React, { useMemo, useState } from "react";
import { ChartCard } from "@/components/charts/ChartCard";
import { Heatmap } from "@/components/charts/Heatmap";
import { DataTable, Segmented, SectionTitle } from "@/components/charts/Primitives";
import { ColoredBars, StackedBars } from "@/components/charts/RC";
import { modelOrder, providerOf, useBundle } from "@/lib/data";
import { compact, num, pct, PROVIDER_COLOR, usd } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const OUTCOMES = [
  { key: "valid", label: "Valid", color: "var(--s3)" },
  { key: "insufficient_names", label: "Fewer than 10", color: "var(--s4)" },
  { key: "excess_names", label: "More than 10", color: "var(--s5)" },
  { key: "format_failure", label: "Format failure", color: "var(--s7)" },
  { key: "refusal", label: "Refusal", color: "var(--s8)" },
  { key: "api_error", label: "API error", color: "var(--muted)" },
];

export function Collection() {
  const { meta, portfolios, analysis } = useBundle();
  const [stage, setStage] = useState<"A" | "B" | "C">("A");
  const models = useMemo(() => modelOrder(meta, new Set(portfolios.map((p) => p.model_requested))), [meta, portfolios]);
  const outcomeRows = useMemo(() => {
    const out: any[] = [];
    for (const m of models) {
      const cell = portfolios.filter((p) => p.model_requested === m && p.stage === stage);
      if (!cell.length) continue;
      const row: any = { model: m };
      for (const o of OUTCOMES) row[o.key] = cell.filter((p) => (p.outcome ?? "api_error") === o.key).length / cell.length;
      out.push(row);
    }
    return out;
  }, [models, portfolios, stage]);
  const refusals: any[] = analysis.refusals?.cells ?? [];
  const prompts = stage === "B" ? ["VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"] : stage === "A" ? ["L1", "L2", "L3", "L4"] : ["L1", "L2", "L3", "L4", "VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"];
  const refusalModels = models.filter((m) => refusals.some((r) => r.model === m && r.stage === stage));
  const refusalMatrix = refusalModels.map((m) => prompts.map((p) => {
    const r = refusals.find((x) => x.model === m && x.prompt_id === p && x.stage === stage);
    return r ? r.refusal : null;
  }));
  const ops: any[] = analysis.ops?.by_model_stage ?? [];
  const costRows = models.map((m) => {
    const rows = ops.filter((o) => o.model === m);
    const cost = rows.reduce((s, r) => s + (r.cost_usd ?? 0), 0);
    const valid = rows.reduce((s, r) => s + (r.valid ?? 0), 0);
    return { model: m, cost, per_valid: valid ? cost / valid : 0, color: PROVIDER_COLOR[providerOf(meta, m)] };
  }).filter((r) => r.cost > 0);
  const stageOps = ops.filter((o) => o.stage === stage);
  return (
    <div>
      <SectionTitle eyebrow="Project" title="Collection">
        Every API call is one row: identity, prompt, settings, timing, usage, cost and outcome (BUILD_BRIEF §4). Refusals and malformed answers are observations and are never retried; transport errors are.
      </SectionTitle>
      <div className="mb-5"><Segmented id="stage" value={stage} onChange={setStage} options={[{ value: "A", label: "Stage A · free-form" }, { value: "B", label: "Stage B · mandates" }, { value: "C", label: "Stage C · search" }]} size="md" /></div>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="Outcome of every call" subtitle="Share of calls by outcome. Only valid books (exactly ten distinct issuers) enter the factor analyses."
          table={<DataTable dense rows={outcomeRows} columns={[{ key: "model", label: "Model" }, ...OUTCOMES.map((o) => ({ key: o.key, label: o.label, align: "right" as const, render: (r: any) => pct(r[o.key], 1) }))]} />}>
          <StackedBars data={outcomeRows} xKey="model" layout="vertical" height={Math.max(260, outcomeRows.length * 30 + 60)} width={130}
            series={OUTCOMES.map((o) => ({ key: o.key, label: o.label, color: o.color }))} />
        </ChartCard>
        <ChartCard title="Refusal rate by prompt and model" subtitle="Paper benchmark: about 26% of bare (L1) requests fail to return a usable portfolio; at most 2% elsewhere.">
          <Heatmap rows={refusalModels} cols={prompts} values={refusalMatrix} mode="sequential" max={0.6} format={(v) => pct(v)} cellHeight={28} />
        </ChartCard>
        <ChartCard title="Cost per model (all stages)" subtitle="Token usage priced from models.yaml, including search fees; batch discount applied where used."
          table={<DataTable dense rows={costRows} columns={[{ key: "model", label: "Model" }, { key: "cost", label: "Cost", align: "right", render: (r) => usd(r.cost) }, { key: "per_valid", label: "Per valid book", align: "right", render: (r) => usd(r.per_valid, 3) }]} />}>
          <ColoredBars data={costRows} xKey="model" yKey="cost" colorKey="color" yFormat={(v) => usd(v, 0)} label height={Math.max(240, costRows.length * 28 + 40)} width={130} />
        </ChartCard>
        <ChartCard title={`Operations · Stage ${stage}`} subtitle="Tokens, searches, retries and latency per model.">
          <div className="max-h-[420px] overflow-auto">
            <DataTable dense rows={stageOps} columns={[
              { key: "model", label: "Model" }, { key: "calls", label: "Calls", align: "right" },
              { key: "valid", label: "Valid", align: "right" },
              { key: "input_tokens", label: "In tok", align: "right", render: (r) => compact(r.input_tokens) },
              { key: "output_tokens", label: "Out tok", align: "right", render: (r) => compact(r.output_tokens) },
              { key: "searches", label: "Searches", align: "right" },
              { key: "retried_calls", label: "Retried", align: "right" },
              { key: "latency_p50", label: "p50 s", align: "right", render: (r) => num(r.latency_p50) },
              { key: "cost_per_valid", label: "$ / valid", align: "right", render: (r) => usd(r.cost_per_valid, 3) },
            ]} />
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
