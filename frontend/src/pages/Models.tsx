import React from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { DataTable, SectionTitle } from "@/components/charts/Primitives";
import { ColoredBars, StackedBars } from "@/components/charts/RC";
import { AnimatedTooltip } from "@/components/ui/animated-tooltip";
import { modelOrder, providerOf, useBundle } from "@/lib/data";
import { CORE_FACTORS, FACTOR_LABEL, num, pct, PROVIDER_COLOR, shortModel, signed } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
function avatar(label: string, color: string) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' rx='32' fill='${color}'/><text x='32' y='39' font-family='sans-serif' font-size='20' font-weight='700' fill='white' text-anchor='middle'>${label}</text></svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

export function Models() {
  const { analysis, meta } = useBundle();
  const gens: any[] = analysis.generations?.rows ?? [];
  const weighting: any[] = analysis.weighting?.rows ?? [];
  const resolution: any[] = analysis.ops?.resolution_by_model ?? [];
  const order = modelOrder(meta);
  const people = order.map((id, i) => {
    const m = meta.roster.find((r) => r.id === id)!;
    const initials = m.provider === "openai" ? "O" : "A";
    return { id: i + 1, name: m.id, designation: `${m.role} · stages ${m.stages.join("")}${m.knowledge_cutoff ? " · cutoff " + m.knowledge_cutoff : ""}`, image: avatar(initials + (m.role === "flagship" ? "★" : ""), m.provider === "openai" ? "#2a78d6" : "#d95926") };
  });
  const jRows = gens.filter((g) => g.jaccard_to_flagship !== null).map((g) => ({ model: shortModel(g.model), value: g.jaccard_to_flagship, color: PROVIDER_COLOR[g.provider] }));
  const resRows = resolution.map((r) => ({ model: r.model, resolved: r.resolved - r.low_confidence, low: r.low_confidence, unresolved: r.unresolved }));
  return (
    <div>
      <SectionTitle eyebrow="New analytics" title="Models: size, generation, sizing and resolution">
        Within each provider: do smaller and older models build different books from the flagship? How do models size positions? How often do their tickers fail to resolve?
      </SectionTitle>
      <div className="mb-8 flex flex-wrap items-center gap-6">
        <div className="flex flex-row items-center"><AnimatedTooltip items={people.slice(0, 6)} /></div>
        <div className="flex flex-row items-center"><AnimatedTooltip items={people.slice(6)} /></div>
        <span className="text-xs text-[var(--muted)]">Hover a model for its role and knowledge cutoff (★ = flagship). Blue = OpenAI, orange = Anthropic.</span>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="Factor profile by size and generation (§8.8)" subtitle="Stage A free-form books. Factor distance is the Euclidean distance of the mean loading vector from the same provider's flagship.">
          <div className="max-h-[440px] overflow-auto">
            <DataTable dense rows={gens} columns={[{ key: "model", label: "Model" }, { key: "role", label: "Role" },
              ...CORE_FACTORS.map((f) => ({ key: f, label: FACTOR_LABEL[f], align: "right" as const, render: (r: any) => signed(r[f]) })),
              { key: "factor_distance_to_flagship", label: "Dist.", align: "right", render: (r) => num(r.factor_distance_to_flagship) }]} />
          </div>
        </ChartCard>
        <ChartCard title="Name overlap with the same provider's flagship" subtitle="Mean Jaccard between each model's books and its provider flagship's books, same prompt.">
          {jRows.length ? <ColoredBars data={jRows} xKey="model" yKey="value" colorKey="color" label height={Math.max(260, jRows.length * 30)} yFormat={(v) => num(v)} width={120} /> : <Empty text="No data." />}
        </ChartCard>
        <ChartCard title="How models size positions" subtitle="Effective N = 1 / Σw² (10 = equal weight). Round weights = share of weights on multiples of 5%. Weight–cap ρ: Spearman correlation between a position's weight and the log market cap (cap-weighting in disguise?).">
          <DataTable dense rows={weighting} columns={[{ key: "model", label: "Model" }, { key: "share_weights_provided", label: "Weights given", align: "right", render: (r) => pct(r.share_weights_provided) },
            { key: "effective_n", label: "Eff. N", align: "right", render: (r) => num(r.effective_n, 1) }, { key: "mean_max_weight", label: "Max wt", align: "right", render: (r) => pct(r.mean_max_weight, 1) },
            { key: "share_round_weights", label: "Round", align: "right", render: (r) => pct(r.share_round_weights) }, { key: "weight_cap_spearman", label: "Weight–cap ρ", align: "right", render: (r) => signed(r.weight_cap_spearman) }]} />
        </ChartCard>
        <ChartCard title="Ticker resolution quality" subtitle="Share of each model's holdings resolved to an issuer (CIQ first, Compustat, then name matching). Unresolved holdings are kept and flagged, never dropped silently.">
          {resRows.length ? <StackedBars data={resRows} xKey="model" layout="vertical" height={Math.max(260, resRows.length * 28 + 50)} width={130}
            series={[{ key: "resolved", label: "Resolved", color: "var(--s3)" }, { key: "low", label: "Low confidence", color: "var(--s4)" }, { key: "unresolved", label: "Unresolved", color: "var(--s8)" }]} /> : <Empty text="No holdings." />}
        </ChartCard>
      </div>
      <div className="mt-6">
        <ChartCard title="Resolution methods" subtitle="How each holding was matched across the whole run.">
          <div className="flex flex-wrap gap-3">
            {Object.entries(analysis.ops?.resolution_methods ?? {}).map(([k, v]: [string, any]) => (
              <div key={k} className="rounded-xl border border-black/10 px-3 py-2 text-xs dark:border-white/10"><div className="text-[var(--ink-2)]">{k}</div><div className="tabular text-lg font-semibold">{Number(v).toLocaleString()}</div></div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-[var(--muted)]">Providers: {Array.from(new Set(resolution.map((r) => providerOf(meta, r.model)))).join(", ")}.</p>
        </ChartCard>
      </div>
    </div>
  );
}
