import React, { useState } from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { Dumbbell } from "@/components/charts/Dumbbell";
import { Heatmap } from "@/components/charts/Heatmap";
import { DataTable, Pill, Segmented, SectionTitle, StatTile } from "@/components/charts/Primitives";
import { StackedBars } from "@/components/charts/RC";
import { useBundle } from "@/lib/data";
import { num, pct, PROVIDER_COLOR, SERIES, shortModel } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const CLASSES = [
  { key: "single_stock_check", label: "Single-stock check", color: SERIES[0] },
  { key: "screen_or_list", label: "Screen / list", color: SERIES[1] },
  { key: "factor_or_market_data", label: "Index / market data", color: SERIES[6] },
  { key: "macro_news", label: "Macro / news", color: SERIES[2] },
  { key: "other", label: "Other", color: "var(--axis)" },
];

export function Search() {
  const { analysis, meta } = useBundle();
  const s = analysis.search ?? {};
  const [measure, setMeasure] = useState<"momentum" | "momentum_12_1">("momentum");
  const mom = s[measure] ?? {};
  const tasks: any[] = mom.by_task ?? [];
  const byModel: any[] = mom.momentum_mandate_by_model ?? [];
  const inv = s.invocation ?? { models: [], prompts: [], rows: [] };
  const invMatrix = inv.models.map((m: string) => inv.prompts.map((p: string) => inv.rows.find((r: any) => r.model === m && r.prompt_id === p)?.share_invoked ?? null));
  const q = analysis.queries ?? {};
  const qRows: any[] = (q.by_prompt ?? []).map((r: any) => ({ ...r, label: `${r.prompt_id} (n=${r.n})` }));
  const gold = q.gold ?? {};
  return (
    <div>
      <SectionTitle eyebrow="Figures 5–7" title="Search and queries">
        Stage C reruns the principal prompts on the four frontier models with web search available; the model decides whether to use it. "Invoked" means at least one executed search event. Tool availability alone does not count.
      </SectionTitle>
      <div className="mb-5"><Segmented id="mom-measure" value={measure} onChange={setMeasure} size="md" options={[{ value: "momentum", label: "Barra-style RSTR" }, { value: "momentum_12_1", label: "Simple 12-1 (robustness)" }]} /></div>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard figure="Fig. 5a" title="What search availability changes, by task" subtitle="Same four models offline (Stages A/B) and with search available (Stage C). Paper: the Momentum mandate moves from −0.38 to +0.43 pooled; free-form barely moves."
          table={<DataTable dense rows={tasks} columns={[{ key: "task", label: "Task" }, { key: "off", label: "Offline", align: "right", render: (r) => num(r.offline?.mean) }, { key: "on", label: "Search available", align: "right", render: (r) => num(r.connected?.mean) }, { key: "inv", label: "…invoked", align: "right", render: (r) => num(r.connected_invoked?.mean) }, { key: "not", label: "…not invoked", align: "right", render: (r) => num(r.connected_not_invoked?.mean) }, { key: "share", label: "Searched", align: "right", render: (r) => pct(r.share_invoked) }]} />}>
          {tasks.length ? <Dumbbell rows={tasks.map((t) => ({ label: t.task.replace(" mandate", ""), before: t.offline?.mean ?? null, after: t.connected?.mean ?? null, note: t.share_invoked !== null ? `${pct(t.share_invoked)} searched` : "", color: (t.connected?.mean ?? 0) - (t.offline?.mean ?? 0) > 0.2 ? "var(--critical)" : "var(--s1)" }))} xLabel="momentum loading" /> : <Empty text="Stage C not collected yet." />}
        </ChartCard>
        <ChartCard figure="Fig. 5b" title="The Momentum mandate, by model" subtitle="Grey arrows: models that did not search. A capable instruction and current information together produce the exposure; neither stands in for the other.">
          {byModel.length ? <Dumbbell rows={byModel.map((r) => ({ label: shortModel(r.model), before: r.offline?.mean ?? null, after: r.connected?.mean ?? null, note: r.share_invoked !== null ? `${pct(r.share_invoked)} searched` : "", color: (r.share_invoked ?? 0) > 0 ? PROVIDER_COLOR[r.provider] : "var(--muted)" }))} xLabel="momentum loading, Momentum mandate" /> : <Empty text="No data." />}
        </ChartCard>
      </div>
      <div className="mt-6">
        <ChartCard figure="Fig. 6" title="Share of connected calls that invoked web search" subtitle="All cells have search enabled; invocation varies by model and by instruction.">
          {inv.models.length ? <Heatmap rows={inv.models} cols={inv.prompts} values={invMatrix} mode="sequential" max={1} rowLabel={shortModel} format={(v) => `${Math.round(v * 100)}`} divider={4} cellHeight={34} /> : <Empty text="No Stage C calls." />}
        </ChartCard>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <ChartCard figure="Fig. 7" title="What they search for" subtitle="Visible queries classified by rules (single-stock checks, screens, index/market data, macro/news, other). Both providers expose queries, so every query is classified. Paper: single-stock checks are 80% of Value queries, 76% Unconstrained, 35% Quality.">
          {qRows.length ? <StackedBars data={qRows} xKey="label" layout="vertical" height={Math.max(260, qRows.length * 36 + 60)} width={150} series={CLASSES} /> : <Empty text="No queries yet." />}
        </ChartCard>
        <div className="grid gap-6">
          <ChartCard title="Do lookups end up in the book?" subtitle="Share of single-stock checks whose stock is in the final portfolio (measured after the fact; it cannot show order of consideration).">
            <div className="grid grid-cols-2 gap-4">
              {(q.lookup_to_portfolio ?? []).map((r: any) => (
                <StatTile key={r.provider} label={r.provider} value={pct(r.share)} sub={`${r.in_final_book} of ${r.lookups_with_named_stock} lookups`} />
              ))}
            </div>
          </ChartCard>
          <ChartCard title="Ordering test" subtitle="Within calls that both screen and check names: does the screen come first?">
            <div className="grid grid-cols-2 gap-4">
              <StatTile label="Screen before first single-stock check" value={pct(q.ordering?.share_screen_first)} sub={`${q.ordering?.screen_first ?? 0} of ${q.ordering?.calls_with_both ?? 0} calls`} />
              <StatTile label="Binomial p (vs 50%)" value={num(q.ordering?.p_binomial, 3)} />
            </div>
          </ChartCard>
          <ChartCard title="Classifier agreement" subtitle="Cohen's κ against the hand-labelled gold set (≥ 200 queries required).">
            <div className="flex items-end gap-6">
              <StatTile label="Cohen's κ" value={num(gold.kappa)} sub={`n = ${gold.n ?? 0}${gold.labellers?.length ? " · " + gold.labellers.join(", ") : ""}`} />
              <div>{gold.meets_minimum ? <Pill tone="good">≥ 200 labels</Pill> : <Pill tone="warn">needs more labels</Pill>}{meta.synthetic && <div className="mt-1"><Pill tone="warn">synthetic gold</Pill></div>}</div>
            </div>
          </ChartCard>
        </div>
      </div>
      {(q.anthropic_tool_versions ?? []).length > 0 && (
        <div className="mt-6">
          <ChartCard title="Anthropic search tool versions" subtitle="Dynamic filtering (web_search_20260318) vs the basic tool (robustness arm, off by default). Nested calls carry a caller field.">
            <DataTable dense rows={q.anthropic_tool_versions} columns={[{ key: "tool_version", label: "Tool" }, { key: "calls", label: "Calls", align: "right" }, { key: "events", label: "Search events", align: "right" }, { key: "share_with_caller", label: "With caller", align: "right", render: (r) => pct(r.share_with_caller) }, { key: "share_errors", label: "Errors", align: "right", render: (r) => pct(r.share_errors, 1) }]} />
          </ChartCard>
        </div>
      )}
    </div>
  );
}
