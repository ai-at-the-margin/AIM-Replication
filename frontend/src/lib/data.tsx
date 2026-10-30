import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Any = any;

export interface RosterModel {
  id: string; provider: string; role: string; generation: string; size_class: string; stages: string[];
  optional: boolean; knowledge_cutoff: string | null; price_in_per_m: number; price_out_per_m: number;
  price_verified: boolean;
}
export interface Meta {
  dataset: string; synthetic: boolean; generated_ts_utc: string; experiment_version: string;
  prompt_version: string; asof: string | null; universe: string | null; roster: RosterModel[];
  prompts: { id: string; family: string; label: string; text: string }[]; planned: Record<string, number>;
}
export interface PortfolioRow {
  call_id: string; stage: string; provider: string; model_requested: string; role: string; prompt_id: string;
  language: string; rep: number; search_enabled: boolean; search_count: number | null; status: string;
  est_cost_usd: number | null; input_tokens: number | null; output_tokens: number | null;
  reasoning_tokens: number | null; latency_s: number | null; attempts: number | null; stop_reason: string | null;
  model_returned: string | null; outcome: string | null; parse_method: string | null; n_names_raw: number | null;
  n_issuers: number | null; weights_provided: boolean | null; size: number | null; value: number | null;
  quality: number | null; momentum: number | null; lowvol: number | null; beta: number | null;
  mom_12_1: number | null; coverage_weight: number | null;
}
export interface Bundle {
  name: string;
  meta: Meta;
  status: Any;
  analysis: Any;
  portfolios: PortfolioRow[];
}
interface DatasetInfo { name: string; exported: boolean; meta: Meta | null }

interface Ctx {
  datasets: DatasetInfo[];
  current: string | null;
  setCurrent: (name: string) => void;
  bundle: Bundle | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  dark: boolean;
  setDark: (dark: boolean) => void;
}

const DataContext = createContext<Ctx | null>(null);

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function DataProvider({ children }: { children: React.ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [current, setCurrentState] = useState<string | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [dark, setDarkState] = useState(() => document.documentElement.classList.contains("dark"));

  const setDark = useCallback((value: boolean) => {
    setDarkState(value);
    document.documentElement.classList.toggle("dark", value);
    try { localStorage.setItem("aim-theme", value ? "dark" : "light"); } catch { /* storage may be blocked */ }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let list: DatasetInfo[] = [];
      try {
        list = (await getJSON<{ datasets: DatasetInfo[] }>("/api/datasets")).datasets.filter((d) => d.exported);
      } catch {
        // static hosting: probe the two dataset folders directly
        for (const name of ["live", "demo"]) {
          try {
            const meta = await getJSON<Meta>(`/data/${name}/meta.json`);
            list.push({ name, exported: true, meta });
          } catch { /* not present */ }
        }
      }
      if (cancelled) return;
      setDatasets(list);
      let preferred: string | null = null;
      try { preferred = localStorage.getItem("aim-dataset"); } catch { /* ignore */ }
      const names = list.map((d) => d.name);
      const pick = preferred && names.includes(preferred) ? preferred : names.includes("live") ? "live" : names[0] ?? null;
      setCurrentState(pick);
      if (!pick) {
        setLoading(false);
        setError("No exported dataset found. Run `aim demo` (synthetic) or the live pipeline, then `aim dashboard serve`.");
      }
    })();
    return () => { cancelled = true; };
  }, [nonce]);

  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const base = `/data/${current}`;
        const [meta, status, analysis, portfolios] = await Promise.all([
          getJSON<Meta>(`${base}/meta.json`),
          getJSON<Any>(`${base}/status.json`),
          getJSON<Any>(`${base}/analysis.json`),
          getJSON<PortfolioRow[]>(`${base}/portfolios.json`),
        ]);
        if (!cancelled) {
          setBundle({ name: current, meta, status, analysis, portfolios });
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [current, nonce]);

  const setCurrent = useCallback((name: string) => {
    setCurrentState(name);
    try { localStorage.setItem("aim-dataset", name); } catch { /* ignore */ }
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const value = useMemo(
    () => ({ datasets, current, setCurrent, bundle, loading, error, reload, dark, setDark }),
    [datasets, current, setCurrent, bundle, loading, error, reload, dark, setDark],
  );
  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): Ctx {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData outside DataProvider");
  return ctx;
}

export function useBundle(): Bundle {
  const { bundle } = useData();
  if (!bundle) throw new Error("bundle not loaded");
  return bundle;
}

export async function loadDetail(dataset: string, callId: string): Promise<Any> {
  return getJSON<Any>(`/data/${dataset}/details/${callId}.json`);
}

export function modelOrder(meta: Meta, present?: Set<string>): string[] {
  const roles = ["flagship", "mainstream", "mid", "small", "previous_flagship", "two_back", "consumer_proxy"];
  const out: string[] = [];
  for (const provider of ["openai", "anthropic"]) {
    for (const role of roles) {
      for (const m of meta.roster) {
        if (m.provider === provider && m.role === role && (!present || present.has(m.id))) out.push(m.id);
      }
    }
  }
  return out;
}

export function providerOf(meta: Meta, model: string): string {
  return meta.roster.find((m) => m.id === model)?.provider ?? "unknown";
}
