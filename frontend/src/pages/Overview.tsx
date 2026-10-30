import { IconArrowRight, IconCircleCheck, IconCircleDashed, IconCircleX, IconLoader2 } from "@tabler/icons-react";
import React, { useMemo } from "react";
import { Dumbbell } from "@/components/charts/Dumbbell";
import { Meter, Pill, StatTile } from "@/components/charts/Primitives";
import { GroupedBars } from "@/components/charts/RC";
import { BentoGrid, BentoGridItem } from "@/components/ui/bento-grid";
import { HoverEffect } from "@/components/ui/card-hover-effect";
import { InfiniteMovingCards } from "@/components/ui/infinite-moving-cards";
import { Spotlight } from "@/components/ui/spotlight-new";
import { TextGenerateEffect } from "@/components/ui/text-generate-effect";
import { useBundle } from "@/lib/data";
import { compact, num, pct, signed, usd } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function statusIcon(status: string) {
  if (status === "done") return <IconCircleCheck size={16} className="text-emerald-500" />;
  if (status === "blocked") return <IconCircleX size={16} className="text-red-500" />;
  if (status === "running" || status === "partial" || status === "check") return <IconLoader2 size={16} className="text-amber-500" />;
  return <IconCircleDashed size={16} className="text-[var(--muted)]" />;
}

export function Overview() {
  const { meta, status, analysis, portfolios } = useBundle();
  const a = analysis ?? {};
  const totals = useMemo(() => {
    let completed = 0, valid = 0, searched = 0, stageC = 0;
    for (const p of portfolios) {
      if (p.status === "completed") completed += 1;
      if (p.outcome === "valid") valid += 1;
      if (p.stage === "C") { stageC += 1; if ((p.search_count ?? 0) > 0) searched += 1; }
    }
    return { completed, valid, searched, stageC };
  }, [portfolios]);
  const planned = (meta.planned.A ?? 0) + (meta.planned.B ?? 0) + (meta.planned.C ?? 0);
  const comparisons: any[] = a.paper_comparison ?? [];
  const find = (metric: string) => comparisons.find((c) => c.metric === metric);
  const overlapA = a.overlap?.A ?? {};
  const overlapRows = ["L1", "L2", "L3", "L4"].map((p) => ({
    prompt: p,
    flagship: overlapA[p]?.a_flagships?.mean ?? null,
    cross: overlapA[p]?.b_cross_provider?.mean ?? null,
  }));
  const tasks: any[] = a.search?.momentum?.by_task ?? [];
  const consensusL1 = a.consensus?.by_stage?.A?.L1;
  const tickerItems = (consensusL1?.top_names ?? []).slice(0, 14).map((n: any) => ({
    quote: n.name ?? n.issuer_id, name: n.ticker ?? "", title: `in ${pct(n.share_of_books)} of L1 books`,
  }));
  const flag = a.exposures?.freeform_flagships_pooled ?? {};
  const valueDelta = (a.mandates?.deltas ?? []).filter((d: any) => d.mandate === "VALUE");
  const meanValueDelta = valueDelta.length ? valueDelta.reduce((s: number, d: any) => s + (d.delta ?? 0), 0) / valueDelta.length : null;
  const findings = [
    { key: "overlap", link: "#/overlap", content: (
      <Finding eyebrow="Figure 1 · Name overlap" title="Agreement depends on the question"
        big={`${num(find("jaccard_L1")?.ours)} → ${num(find("jaccard_L4")?.ours)}`}
        text={`Cross-provider Jaccard from the bare request to the fund-manager brief. Paper: ${num(find("jaccard_L1")?.paper)} → ${num(find("jaccard_L4")?.paper)}.`} />) },
    { key: "factors", link: "#/factors", content: (
      <Finding eyebrow="Figures 2–3 · Factor profiles" title="Different names, similar positions"
        big={`Size ${signed(flag.size)} · Quality ${signed(flag.quality)}`}
        text={`Flagship free-form books: momentum ${signed(flag.momentum)}, value ${signed(flag.value)}. Paper: size +0.55, quality +0.49.`} />) },
    { key: "mandates", link: "#/mandates", content: (
      <Finding eyebrow="Figure 4 · Mandates" title="A value mandate moves the book"
        big={`Δ value ${signed(meanValueDelta)}`}
        text="Mean lift in value loading versus each model's own Unconstrained book (search off)." />) },
    { key: "search", link: "#/search", content: (
      <Finding eyebrow="Figure 5 · Search" title="Current information fixes momentum"
        big={`${signed(find("momentum_mandate_offline")?.ours)} → ${signed(find("momentum_mandate_connected")?.ours)}`}
        text="Momentum mandate loading, offline vs with web search available. Paper: −0.38 → +0.43." />) },
    { key: "queries", link: "#/search", content: (
      <Finding eyebrow="Figure 7 · Queries" title="Search checks names, not universes"
        big={`${pct(find("single_stock_value")?.ours)} single-stock`}
        text={`Share of Value-mandate queries that check one stock. Paper: ${pct(find("single_stock_value")?.paper)}.`} />) },
    { key: "information", link: "#/information", content: (
      <Finding eyebrow="New · Information date" title="When does each model's market end?"
        big={`${(a.staleness?.rows ?? []).filter((r: any) => r.cell === "offline").length} models dated`}
        text="Offline momentum books re-measured 0–18 months back; the peak dates each model's information." />) },
  ];
  return (
    <div>
      <div className="relative mb-8 overflow-hidden rounded-3xl border border-black/10 bg-[var(--surface)] px-6 py-12 md:px-12 md:py-16 dark:border-white/10 dark:bg-black/[0.96]">
        <Spotlight />
        <div className="relative z-10 max-w-4xl">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Pill tone={meta.synthetic ? "warn" : "good"}>{meta.synthetic ? "Synthetic demo dataset" : "Live dataset"}</Pill>
            <Pill>experiment {meta.experiment_version}</Pill>
            <Pill>prompts {meta.prompt_version}</Pill>
          </div>
          <h1 className="bg-gradient-to-b from-neutral-900 to-neutral-500 bg-clip-text text-4xl font-bold tracking-tight text-transparent md:text-6xl dark:from-neutral-50 dark:to-neutral-400">
            AI at the Margin
          </h1>
          <TextGenerateEffect duration={0.4} className="mt-3 max-w-3xl text-base font-normal md:text-lg [&_div]:!text-[var(--ink-2)] [&_div]:!text-base md:[&_div]:!text-lg [&_div]:!font-normal [&_div]:!leading-relaxed"
            words="What would the marginal AI investor buy? Twelve OpenAI and Anthropic models build ten-stock portfolios under four framings, four mandates and with web search available; every book is resolved to issuers and measured on a Barra-style factor model built from WRDS." />
        </div>
      </div>

      <BentoGrid className="mx-0 mb-10 max-w-none md:auto-rows-[11rem] md:grid-cols-4">
        <BentoGridItem className="md:col-span-2" header={
          <StatTile label="Calls completed" value={`${totals.completed.toLocaleString()} / ${planned.toLocaleString()}`}
            sub={`A ${meta.planned.A} · B ${meta.planned.B} · C ${meta.planned.C} planned`}>
            <Meter value={totals.completed} max={planned} label="collection progress" />
          </StatTile>} />
        <BentoGridItem header={<StatTile label="Valid portfolios" value={totals.valid.toLocaleString()} sub={`${pct(totals.valid / Math.max(1, totals.completed))} of completed calls`} />} />
        <BentoGridItem header={<StatTile label="Spend" value={usd(status?.budget?.spent_usd)} sub={`estimate ${usd(status?.budget?.estimated_total_usd)} for the full design`} />} />
        <BentoGridItem header={<StatTile label="Holdings resolved" value={pct(a.ops?.resolution_rate, 1)} sub="target ≥ 99% (Phase 4)" />} />
        <BentoGridItem header={<StatTile label="Search invoked (Stage C)" value={pct(totals.searched / Math.max(1, totals.stageC))} sub={`${totals.searched} of ${totals.stageC} connected calls`} />} />
        <BentoGridItem header={<StatTile label="Estimation universe" value={compact(a.factor_runs?.[`${meta.asof}:${meta.universe}`]?.universe_count)} sub={`${meta.universe} · as-of ${meta.asof}`} />} />
        <BentoGridItem header={<StatTile label="Refusals at L1" value={pct(find("refusal_L1")?.ours)} sub="paper ≈ 26%; ≤ 2% elsewhere" />} />
      </BentoGrid>

      <h2 className="mb-1 text-xl font-semibold text-[var(--ink)]">Headline findings</h2>
      <p className="mb-2 text-sm text-[var(--ink-2)]">Each card links to the page that explains it. Numbers update whenever the pipeline re-exports.</p>
      <HoverEffect items={findings} className="-mx-2 mb-8" />

      {tickerItems.length > 0 && (
        <div className="mb-10">
          <h2 className="mb-1 text-xl font-semibold text-[var(--ink)]">The names models reach for first</h2>
          <p className="mb-2 text-sm text-[var(--ink-2)]">Most frequent issuers in bare-request (L1) books, across all models.</p>
          <InfiniteMovingCards items={tickerItems} direction="left" speed="slow" />
        </div>
      )}

      <div className="mb-10 grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-black/10 bg-[var(--surface)] p-5 dark:border-white/10">
          <div className="mb-2 flex items-center justify-between"><h3 className="text-[15px] font-semibold">Name overlap by framing</h3><a href="#/overlap" className="text-xs text-[var(--s1)]">Figure 1 <IconArrowRight size={12} className="inline" /></a></div>
          <GroupedBars data={overlapRows} xKey="prompt" height={240} yDomain={[0, 1]}
            series={[{ key: "flagship", label: "Flagship pair", color: "var(--s1)" }, { key: "cross", label: "All cross-provider pairs", color: "var(--s2)" }]} />
        </div>
        <div className="rounded-2xl border border-black/10 bg-[var(--surface)] p-5 dark:border-white/10">
          <div className="mb-2 flex items-center justify-between"><h3 className="text-[15px] font-semibold">Momentum: search off vs available</h3><a href="#/search" className="text-xs text-[var(--s1)]">Figure 5 <IconArrowRight size={12} className="inline" /></a></div>
          <Dumbbell rows={tasks.map((t: any) => ({ label: t.task.replace(" mandate", ""), before: t.offline?.mean ?? null, after: t.connected?.mean ?? null,
            note: t.share_invoked !== null ? `${pct(t.share_invoked)} searched` : "", color: (t.connected?.mean ?? 0) - (t.offline?.mean ?? 0) > 0.2 ? "var(--critical)" : "var(--s1)" }))} />
        </div>
      </div>

      <h2 className="mb-3 text-xl font-semibold text-[var(--ink)]">Build phases</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(status?.phases ?? []).map((p: any) => (
          <a key={p.phase} href="#/pipeline" className="rounded-xl border border-black/10 bg-[var(--surface)] p-4 transition hover:border-black/25 dark:border-white/10 dark:hover:border-white/25">
            <div className="flex items-center justify-between text-xs text-[var(--muted)]"><span>Phase {p.phase}</span>{statusIcon(p.status)}</div>
            <div className="mt-1 text-sm font-semibold text-[var(--ink)]">{p.name}</div>
            <div className="mt-1 text-xs capitalize text-[var(--ink-2)]">{p.status}</div>
          </a>
        ))}
      </div>
    </div>
  );
}

function Finding({ eyebrow, title, big, text }: { eyebrow: string; title: string; big: string; text: string }) {
  return (
    <div>
      <div className="text-[11px] font-semibold tracking-wide text-[var(--s1)] uppercase">{eyebrow}</div>
      <div className="mt-2 text-base font-semibold text-[var(--ink)]">{title}</div>
      <div className="tabular mt-3 text-2xl font-semibold tracking-tight text-[var(--ink)]">{big}</div>
      <p className="mt-2 text-[13px] leading-relaxed text-[var(--ink-2)]">{text}</p>
    </div>
  );
}
