import { IconX } from "@tabler/icons-react";
import { AnimatePresence, motion } from "motion/react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Pill, SectionTitle } from "@/components/charts/Primitives";
import { PlaceholdersAndVanishInput } from "@/components/ui/placeholders-and-vanish-input";
import { useOutsideClick } from "@/hooks/use-outside-click";
import { loadDetail, modelOrder, useBundle, type PortfolioRow } from "@/lib/data";
import { diverging } from "@/lib/colors";
import { useData } from "@/lib/data";
import { CORE_FACTORS, FACTOR_LABEL, num, pct, PROVIDER_COLOR, sectorName, shortModel, signed, usd } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
const OUTCOME_TONE: Record<string, "good" | "warn" | "bad" | "neutral"> = {
  valid: "good", insufficient_names: "warn", excess_names: "warn", format_failure: "bad", refusal: "bad", api_error: "bad",
};
const CLASS_COLOR: Record<string, string> = {
  single_stock_check: "var(--s1)", screen_or_list: "var(--s2)", factor_or_market_data: "var(--s7)", macro_news: "var(--s3)", other: "var(--axis)",
};

export function Explorer() {
  const { meta, portfolios, name } = useBundle() as any;
  const [query, setQuery] = useState("");
  const [typing, setTyping] = useState("");
  const [stage, setStage] = useState("all");
  const [model, setModel] = useState("all");
  const [prompt, setPrompt] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [limit, setLimit] = useState(60);
  const [active, setActive] = useState<PortfolioRow | null>(null);
  const models = useMemo(() => modelOrder(meta, new Set(portfolios.map((p: PortfolioRow) => p.model_requested))), [meta, portfolios]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (portfolios as any[]).filter((p) => (stage === "all" || p.stage === stage) && (model === "all" || p.model_requested === model)
      && (prompt === "all" || p.prompt_id === prompt) && (outcome === "all" || (p.outcome ?? "api_error") === outcome)
      && (!q || p.call_id.includes(q) || p.model_requested.toLowerCase().includes(q) || (p.names ?? "").toLowerCase().includes(q)));
  }, [portfolios, query, stage, model, prompt, outcome]);
  useEffect(() => setLimit(60), [query, stage, model, prompt, outcome]);
  const select = (value: string, set: (v: string) => void, options: string[], label: string) => (
    <label className="flex items-center gap-1.5 text-xs text-[var(--ink-2)]">{label}
      <select value={value} onChange={(e) => set(e.target.value)} className="rounded-lg border border-black/10 bg-[var(--surface)] px-2 py-1 text-xs text-[var(--ink)] dark:border-white/15">
        <option value="all">all</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
  return (
    <div>
      <SectionTitle eyebrow="Data" title="Portfolio explorer">
        Every call: the exact response, the parsed holdings with how each ticker was resolved, the book's factor loadings and every search query the model ran. Search by issuer name, ticker, model or call id.
      </SectionTitle>
      <div className="mb-4">
        <PlaceholdersAndVanishInput
          placeholders={["Search a company, e.g. Nvidia", "Try a ticker: TSM, 0700, ASML", "Filter by model: claude-fable-5-1", "Paste a call id"]}
          onChange={(e) => setTyping(e.target.value)}
          onSubmit={(e) => { e.preventDefault(); setQuery(typing); }}
        />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {select(stage, setStage, ["A", "B", "C"], "Stage")}
        {select(model, setModel, models, "Model")}
        {select(prompt, setPrompt, ["L1", "L2", "L3", "L4", "VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"], "Prompt")}
        {select(outcome, setOutcome, ["valid", "insufficient_names", "excess_names", "format_failure", "refusal", "api_error"], "Outcome")}
        {query && <button onClick={() => setQuery("")} className="inline-flex items-center gap-1 rounded-full bg-[var(--s1)]/15 px-2 py-1 text-xs text-[var(--s1)]">“{query}” <IconX size={12} /></button>}
        <span className="ml-auto text-xs text-[var(--muted)]">{filtered.length.toLocaleString()} calls</span>
      </div>
      <div className="overflow-hidden rounded-2xl border border-black/10 bg-[var(--surface)] dark:border-white/10">
        <div className="hidden grid-cols-[110px_1.3fr_1fr_110px_70px_repeat(4,64px)_70px] gap-2 border-b border-black/10 px-4 py-2 text-[11px] font-medium text-[var(--ink-2)] md:grid dark:border-white/10">
          <span>Call</span><span>Model</span><span>Prompt</span><span>Outcome</span><span>Search</span>
          {["size", "value", "quality", "momentum"].map((f) => <span key={f} className="text-right">{FACTOR_LABEL[f]}</span>)}<span className="text-right">Cost</span>
        </div>
        {filtered.slice(0, limit).map((p: any) => (
          <motion.button layoutId={`card-${p.call_id}`} key={p.call_id} onClick={() => setActive(p)}
            className="grid w-full grid-cols-2 gap-2 border-b border-black/5 px-4 py-2 text-left text-xs transition hover:bg-black/[0.03] md:grid-cols-[110px_1.3fr_1fr_110px_70px_repeat(4,64px)_70px] dark:border-white/5 dark:hover:bg-white/[0.04]">
            <span className="font-mono text-[11px] text-[var(--muted)]">{p.call_id.slice(0, 10)}</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 shrink-0 rounded-full" style={{ background: PROVIDER_COLOR[p.provider] }} />{p.model_requested}</span>
            <span className="text-[var(--ink-2)]">{p.stage} · {p.prompt_id} · rep {p.rep}{p.language !== "en" ? ` · ${p.language}` : ""}</span>
            <span><Pill tone={OUTCOME_TONE[p.outcome ?? "api_error"] ?? "neutral"}>{p.outcome ?? "–"}</Pill></span>
            <span className="text-[var(--ink-2)]">{p.search_enabled ? `${p.search_count ?? 0}×` : "off"}</span>
            {["size", "value", "quality", "momentum"].map((f) => <span key={f} className="tabular hidden text-right md:block">{signed(p[f])}</span>)}
            <span className="tabular hidden text-right text-[var(--ink-2)] md:block">{usd(p.est_cost_usd, 3)}</span>
          </motion.button>
        ))}
        {filtered.length > limit && (
          <button onClick={() => setLimit((l) => l + 120)} className="w-full py-3 text-xs font-medium text-[var(--s1)] hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">Show more ({(filtered.length - limit).toLocaleString()} remaining)</button>
        )}
      </div>
      <AnimatePresence>{active && <DetailModal row={active} dataset={name} onClose={() => setActive(null)} />}</AnimatePresence>
    </div>
  );
}

function DetailModal({ row, dataset, onClose }: { row: PortfolioRow; dataset: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark } = useData();
  const { meta } = useBundle();
  const [detail, setDetail] = useState<any>(null);
  const [tab, setTab] = useState<"holdings" | "response" | "search">("holdings");
  useOutsideClick(ref, onClose);
  useEffect(() => {
    loadDetail(dataset, row.call_id).then(setDetail).catch(() => setDetail({ error: true }));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dataset, row.call_id, onClose]);
  const prompt = meta.prompts.find((p) => p.id === row.prompt_id);
  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
      <div className="fixed inset-0 z-50 grid place-items-center p-3 md:p-8">
        <motion.div layoutId={`card-${row.call_id}`} ref={ref}
          className="flex h-full max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-black/10 bg-[var(--surface)] shadow-2xl dark:border-white/10">
          <div className="flex items-start justify-between gap-4 border-b border-black/10 p-5 dark:border-white/10">
            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]"><span className="font-mono">{row.call_id}</span><Pill tone={OUTCOME_TONE[row.outcome ?? "api_error"] ?? "neutral"}>{row.outcome}</Pill>{row.search_enabled && <Pill tone="info">search {row.search_count ?? 0}×</Pill>}</div>
              <div className="mt-1 text-lg font-semibold text-[var(--ink)]">{row.model_requested} · {prompt?.label ?? row.prompt_id} · rep {row.rep}</div>
              <div className="mt-0.5 text-xs text-[var(--ink-2)]">returned {row.model_returned ?? "–"} · {row.input_tokens ?? "–"} in / {row.output_tokens ?? "–"} out tokens · {usd(row.est_cost_usd, 4)} · stop {row.stop_reason ?? "–"} · parsed by {row.parse_method ?? "–"}</div>
            </div>
            <button onClick={onClose} className="rounded-full p-2 hover:bg-black/5 dark:hover:bg-white/10" aria-label="Close"><IconX size={18} /></button>
          </div>
          <div className="grid grid-cols-3 gap-2 border-b border-black/10 px-5 py-3 sm:grid-cols-6 dark:border-white/10">
            {CORE_FACTORS.map((f) => {
              const v = (row as any)[f];
              const c = diverging(v, 1.5, dark);
              return <div key={f} className="rounded-lg px-2 py-1.5 text-center" style={{ background: c.bg, color: c.fg }}><div className="text-[10px] opacity-80">{FACTOR_LABEL[f]}</div><div className="tabular text-sm font-semibold">{signed(v)}</div></div>;
            })}
          </div>
          <div className="flex gap-1 px-5 pt-3">
            {(["holdings", "response", "search"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={"rounded-full px-3 py-1 text-xs font-medium capitalize " + (tab === t ? "bg-neutral-900 text-white dark:bg-white dark:text-black" : "text-[var(--ink-2)] hover:bg-black/5 dark:hover:bg-white/5")}>
                {t === "search" ? `search (${detail?.searches?.length ?? 0})` : t}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-auto p-5">
            {!detail && <div className="text-sm text-[var(--muted)]">Loading…</div>}
            {detail?.error && <div className="text-sm text-red-500">Detail file not found.</div>}
            {detail && !detail.error && tab === "holdings" && (
              <table className="w-full text-xs">
                <thead><tr className="border-b border-black/10 text-left text-[var(--ink-2)] dark:border-white/10">
                  <th className="py-1.5 pr-2">#</th><th className="pr-2">As written</th><th className="pr-2">Resolved issuer</th><th className="pr-2">Method</th><th className="pr-2 text-right">Weight</th><th className="pr-2">Sector</th>
                  {["size", "value", "quality", "momentum"].map((f) => <th key={f} className="pr-2 text-right">{FACTOR_LABEL[f]}</th>)}<th className="text-right">Cap $bn</th>
                </tr></thead>
                <tbody>
                  {detail.holdings.map((h: any) => (
                    <tr key={h.position_idx} className="border-b border-black/5 dark:border-white/5">
                      <td className="py-1.5 pr-2 text-[var(--muted)]">{h.position_idx + 1}</td>
                      <td className="pr-2"><span className="font-mono">{h.raw_ticker}</span> <span className="text-[var(--muted)]">{h.raw_exchange}</span><div className="text-[11px] text-[var(--ink-2)]">{h.raw_name}</div></td>
                      <td className="pr-2">{h.resolved_name ?? <span className="text-red-500">unresolved</span>}{h.duplicate_of !== null && h.duplicate_of !== undefined && <span className="ml-1"><Pill tone="warn">same issuer as #{Number(h.duplicate_of) + 1}</Pill></span>}<div className="text-[11px] text-[var(--muted)]">{h.exchange_code ?? ""} {h.country ?? ""}{h.is_adr ? " · ADR" : ""}{h.is_china_a_share ? " · A-share" : ""}</div></td>
                      <td className="pr-2 text-[var(--ink-2)]">{h.resolution_method}<div className="text-[11px] text-[var(--muted)]">conf {num(h.resolution_confidence)}</div></td>
                      <td className="tabular pr-2 text-right">{pct(h.weight_norm, 1)}</td>
                      <td className="pr-2 text-[var(--ink-2)]">{sectorName(h.gics_sector)}</td>
                      {["size", "value", "quality", "momentum"].map((f) => <td key={f} className="tabular pr-2 text-right">{signed(h.exposure?.[f])}</td>)}
                      <td className="tabular text-right">{num(h.exposure?.mcap_bn, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {detail && !detail.error && tab === "response" && (
              <div className="space-y-4">
                {prompt && <details className="rounded-xl border border-black/10 p-3 text-xs dark:border-white/10"><summary className="cursor-pointer font-medium">Prompt sent</summary><pre className="mt-2 whitespace-pre-wrap text-[var(--ink-2)]">{prompt.text}</pre></details>}
                {detail.reasoning_excerpt && <details className="rounded-xl border border-black/10 p-3 text-xs dark:border-white/10"><summary className="cursor-pointer font-medium">Reasoning ({detail.reasoning_word_count} words, excerpt)</summary><pre className="mt-2 whitespace-pre-wrap text-[var(--ink-2)]">{detail.reasoning_excerpt}</pre></details>}
                <pre className="whitespace-pre-wrap rounded-xl bg-black/[0.03] p-4 font-mono text-[12px] leading-relaxed text-[var(--ink)] dark:bg-white/[0.04]">{detail.final_text || "(empty response)"}</pre>
              </div>
            )}
            {detail && !detail.error && tab === "search" && (
              <ol className="space-y-2">
                {detail.searches.length === 0 && <li className="text-sm text-[var(--muted)]">No search events.</li>}
                {detail.searches.map((s: any) => (
                  <li key={s.idx} className="flex items-start gap-3 rounded-xl border border-black/10 p-3 text-xs dark:border-white/10">
                    <span className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: CLASS_COLOR[s.class] ?? "var(--axis)" }} />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-[var(--ink)]">{s.query ?? <i className="text-[var(--muted)]">({s.type}, no query text)</i>}</div>
                      <div className="mt-0.5 text-[11px] text-[var(--muted)]">{s.class ?? "unclassified"} · {s.type} · {s.n_results} results{s.caller ? " · nested (dynamic filtering)" : ""}{s.error ? ` · error ${s.error}` : ""}</div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </motion.div>
      </div>
    </>
  );
}

export { shortModel };
