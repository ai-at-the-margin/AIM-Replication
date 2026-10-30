import { IconCheck, IconX } from "@tabler/icons-react";
import React from "react";
import { ChartCard } from "@/components/charts/ChartCard";
import { DataTable, Pill, SectionTitle } from "@/components/charts/Primitives";
import { GroupedBars } from "@/components/charts/RC";
import { Timeline } from "@/components/ui/timeline";
import { useBundle } from "@/lib/data";
import { num, usd } from "@/lib/format";
import { statusIcon } from "./Overview";

/* eslint-disable @typescript-eslint/no-explicit-any */
const STATUS_TONE: Record<string, "good" | "warn" | "bad" | "neutral" | "info"> = {
  done: "good", partial: "warn", check: "warn", running: "info", blocked: "bad", todo: "neutral", designed: "neutral",
};

export function Pipeline() {
  const { meta, status } = useBundle();
  const phases: any[] = status?.phases ?? [];
  const verification = status?.verification ?? {};
  const providers = verification.providers ?? {};
  const wrds = verification.wrds ?? {};
  const sources: any[] = wrds.sources ?? [];
  const probes = wrds.probes ?? {};
  const budget = status?.budget ?? {};
  const budgetRows = ["A", "B", "C"].map((s) => ({ stage: `Stage ${s}`, estimate: budget.by_stage?.[s] ?? 0, cap: budget.caps?.[s] ?? 0 }));
  const timeline = phases.map((p: any) => ({
    title: `Phase ${p.phase}`,
    content: (
      <div className="mb-4 rounded-2xl border border-black/10 bg-[var(--surface)] p-5 dark:border-white/10">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {statusIcon(p.status)}
          <span className="text-base font-semibold text-[var(--ink)]">{p.name}</span>
          <Pill tone={STATUS_TONE[p.status] ?? "neutral"}>{p.status}</Pill>
        </div>
        <ul className="space-y-1.5">
          {(p.criteria ?? []).map((c: any, i: number) => (
            <li key={i} className="flex items-start gap-2 text-sm text-[var(--ink-2)]">
              {c.ok ? <IconCheck size={16} className="mt-0.5 shrink-0 text-emerald-500" /> : <IconX size={16} className="mt-0.5 shrink-0 text-[var(--muted)]" />}
              <span>{c.text}</span>
            </li>
          ))}
        </ul>
        {p.detail && <p className="mt-2 text-xs text-[var(--muted)]">{p.detail}</p>}
      </div>
    ),
  }));
  return (
    <div>
      <SectionTitle eyebrow="Project" title="Pipeline, verification and data sources">
        Live acceptance checks for each build phase (BUILD_BRIEF §11), what <code>aim verify</code> found, which WRDS table fed each input, and how the run differs from the paper.
      </SectionTitle>
      <Timeline data={timeline} title="Build phases" description="Ticks are computed from the database and verification state at export time." />

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <ChartCard title="Provider verification" subtitle="Model ids confirmed against each provider's model list, plus one search-enabled test call whose queries must be captured.">
          <div className="space-y-4">
            {Object.keys(providers).length === 0 && <p className="text-sm text-[var(--muted)]">Not run yet: <code>aim verify</code>.</p>}
            {Object.entries(providers).map(([name, p]: [string, any]) => (
              <div key={name} className="rounded-xl border border-black/10 p-3 dark:border-white/10">
                <div className="mb-1 flex items-center gap-2 text-sm font-semibold capitalize">{name}
                  <Pill tone={p.key_present ? "good" : "bad"}>{p.key_present ? "key present" : "no key"}</Pill>
                  {p.search_test && <Pill tone={p.search_test.ok ? "good" : "bad"}>search test {p.search_test.ok ? "ok" : "failed"}</Pill>}
                </div>
                {p.list_error && <p className="text-xs text-red-500">{p.list_error}</p>}
                <p className="text-xs text-[var(--ink-2)]">confirmed: {(p.models_ok ?? []).join(", ") || "–"}</p>
                {(p.models_missing ?? []).length > 0 && <p className="text-xs text-amber-600 dark:text-amber-400">missing: {p.models_missing.join(", ")}</p>}
                {p.search_test?.queries_captured && <p className="mt-1 text-xs text-[var(--muted)]">captured queries: {p.search_test.queries_captured.slice(0, 3).join(" · ")}</p>}
              </div>
            ))}
          </div>
        </ChartCard>
        <ChartCard title="Budget" subtitle={`Estimated cost of the full design (Stages A and B at batch prices) against the per-stage caps. Spent so far: ${usd(budget.spent_usd)}.`}
          table={<DataTable columns={[{ key: "stage", label: "Stage" }, { key: "estimate", label: "Estimate", align: "right", render: (r) => usd(r.estimate) }, { key: "cap", label: "Cap", align: "right", render: (r) => usd(r.cap) }]} rows={budgetRows} />}>
          <GroupedBars data={budgetRows} xKey="stage" height={250} yFormat={(v) => usd(v, 0)}
            series={[{ key: "estimate", label: "Estimate (USD)", color: "var(--s1)" }, { key: "cap", label: "Cap (USD)", color: "var(--axis)" }]} />
        </ChartCard>
      </div>

      <div className="mt-6">
        <ChartCard title="WRDS: source chosen for each input" subtitle={`${wrds.connected ? "Connected" : "Not connected"} to ${wrds.host ?? "WRDS"}. Primary → fallback per input (BUILD_BRIEF §2.2); the pipeline halts only when a required input has no source.${wrds.error ? " Error: " + wrds.error : ""}`}>
          <DataTable dense rows={sources} columns={[
            { key: "input", label: "Input" },
            { key: "status", label: "Status", render: (r) => <Pill tone={r.status === "ok" ? "good" : r.status === "HALT" ? "bad" : "warn"}>{r.status}</Pill> },
            { key: "source_used", label: "Source" },
            { key: "fallback_used", label: "Fallback", render: (r) => (r.fallback_used ? "yes" : "no") },
            { key: "effective_latest_date", label: "Effective latest" },
            { key: "notes", label: "Notes", render: (r) => <span className="text-[var(--ink-2)]">{r.notes}</span> },
          ]} />
        </ChartCard>
      </div>

      {Object.keys(probes).length > 0 && (
        <div className="mt-6">
          <ChartCard title="Effective latest dates" subtitle="Latest date with at least half the median row count of the previous 20 trading days; future-dated rows are discarded and counted (BUILD_BRIEF §2.4).">
            <DataTable dense rows={Object.entries(probes).map(([k, v]: [string, any]) => ({ key: k, ...v }))} columns={[
              { key: "key", label: "Logical table" },
              { key: "ok", label: "Readable", render: (r) => (r.ok ? "yes" : "no") },
              { key: "effective_latest_date", label: "Effective latest" },
              { key: "raw_max_date", label: "Raw max" },
              { key: "future_rows_discarded", label: "Future rows dropped", align: "right" },
              { key: "freshness_detail", label: "Detail", render: (r) => <span className="text-[var(--ink-2)]">{r.freshness_detail ?? r.error ?? ""}</span> },
            ]} />
          </ChartCard>
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <ChartCard title="Model roster" subtitle="12 models across two providers; Stage C uses the flagship and mainstream frontier model of each.">
          <DataTable dense rows={meta.roster.filter((m) => !m.optional)} columns={[
            { key: "id", label: "Model" }, { key: "provider", label: "Provider" }, { key: "role", label: "Role" },
            { key: "stages", label: "Stages", render: (r) => r.stages.join(" ") },
            { key: "knowledge_cutoff", label: "Cutoff", render: (r) => r.knowledge_cutoff ?? "–" },
            { key: "price", label: "$ in / out per M", align: "right", render: (r) => `${num(r.price_in_per_m)} / ${num(r.price_out_per_m)}${r.price_verified ? "" : " *"}` },
          ]} />
          <p className="mt-2 text-[11px] text-[var(--muted)]">* placeholder price, set conservatively until confirmed.</p>
        </ChartCard>
        <ChartCard title="Deviations from the paper" subtitle="Also recorded in docs/DEVIATIONS.md.">
          <DataTable dense rows={status?.deviations ?? []} columns={[
            { key: "item", label: "Item" }, { key: "paper", label: "Paper" }, { key: "ours", label: "Ours" },
          ]} />
        </ChartCard>
      </div>

      {(status?.source_log ?? []).length > 0 && (
        <div className="mt-6">
          <ChartCard title="source_log" subtitle="Which source fed each input on each as-of date, with row counts.">
            <div className="max-h-80 overflow-auto">
              <DataTable dense rows={status.source_log} columns={[
                { key: "asof_date", label: "As-of" }, { key: "input", label: "Input" }, { key: "source_used", label: "Source" },
                { key: "fallback_used", label: "Fallback", render: (r) => (r.fallback_used ? "yes" : "no") },
                { key: "rows", label: "Rows", align: "right" }, { key: "notes", label: "Notes" },
              ]} />
            </div>
          </ChartCard>
        </div>
      )}
    </div>
  );
}
