import React, { useMemo, useState } from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { DataTable, Segmented, SectionTitle } from "@/components/charts/Primitives";
import { Lines, Scatterplot } from "@/components/charts/RC";
import { useBundle } from "@/lib/data";
import { num, PROVIDER_COLOR, SERIES, shortModel, signed } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function Information() {
  const { analysis, meta } = useBundle();
  const st = analysis.staleness ?? {};
  const curves: any[] = st.curves ?? [];
  const rows: any[] = st.rows ?? [];
  const [provider, setProvider] = useState<"openai" | "anthropic">("openai");
  const offline = curves.filter((c) => c.cell === "offline" && meta.roster.find((m) => m.id === c.model)?.provider === provider);
  const connected = curves.filter((c) => c.cell !== "offline");
  const lags: number[] = st.lags ?? [];
  const lineData = lags.map((lag, i) => {
    const row: any = { lag };
    for (const c of offline) row[c.model] = c.values[i];
    return row;
  });
  const connectedData = lags.map((lag, i) => {
    const row: any = { lag };
    for (const c of connected) row[c.model] = c.values[i];
    return row;
  });
  const scatter = useMemo(() => ["openai", "anthropic"].map((p) => ({
    name: p, color: PROVIDER_COLOR[p],
    points: rows.filter((r) => r.cell === "offline" && r.provider === p && r.stated_cutoff_lag_months !== null).map((r) => ({ x: r.stated_cutoff_lag_months, y: r.implied_lag_months, model: r.model })),
  })), [rows]);
  return (
    <div>
      <SectionTitle eyebrow="New analytics" title="Implied information date">
        The paper attributes the offline momentum failure to dated information but cannot date it. We can. Each model's offline Momentum-mandate books are re-measured on 12-1 month momentum computed at successively earlier dates (T, T−1m, …, T−18m). The lag at which the books look most momentum-like is the model's <b>implied information date</b>, set next to its stated knowledge cutoff. A model that searched should peak at lag 0.
      </SectionTitle>
      <div className="mb-5"><Segmented id="info-prov" value={provider} onChange={setProvider} size="md" options={[{ value: "openai", label: "OpenAI models" }, { value: "anthropic", label: "Anthropic models" }]} /></div>
      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <ChartCard title="Offline Momentum books, momentum measured k months back" subtitle={`Mean book loading on 12-1 momentum (z-score vs the universe) measured at each lag. Measurement dates: lag 0 = ${st.measure_dates?.["0"] ?? "T"}, lag 12 = ${st.measure_dates?.["12"] ?? "T−12m"}.`}
          table={<DataTable dense rows={lineData} columns={[{ key: "lag", label: "Lag (months)" }, ...offline.map((c) => ({ key: c.model, label: shortModel(c.model), align: "right" as const, render: (r: any) => signed(r[c.model]) }))]} />}>
          {lineData.length ? <Lines data={lineData} xKey="lag" xType="number" height={340} refLine={0} dots={false} xLabel="months before the as-of date" yLabel="book momentum (sd)"
            series={offline.map((c, i) => ({ key: c.model, label: shortModel(c.model), color: SERIES[i % 8] }))} /> : <Empty text="Needs Stage B books and a factor build with momentum history." />}
        </ChartCard>
        <ChartCard title="Implied vs stated" subtitle="Each dot is a model: stated knowledge-cutoff lag (x) against the lag of peak momentum (y). Points on the diagonal mean the books reflect the market as of the model's cutoff.">
          {rows.length ? <Scatterplot groups={scatter} xLabel="stated cutoff lag (months)" yLabel="implied lag (months)" height={300}
            tip={(p) => [{ label: "model", value: p.model }, { label: "stated", value: num(p.x, 1) }, { label: "implied", value: String(p.y) }]} /> : <Empty text="No cutoffs configured (models.yaml knowledge_cutoff)." />}
        </ChartCard>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <ChartCard title="Connected Momentum books (search invoked)" subtitle="The same measurement for books built after searching: these should peak at lag 0.">
          {connected.length ? <Lines data={connectedData} xKey="lag" xType="number" height={300} refLine={0} dots={false} xLabel="months before the as-of date"
            series={connected.map((c, i) => ({ key: c.model, label: shortModel(c.model), color: SERIES[i % 8] }))} /> : <Empty text="No searched Momentum books." />}
        </ChartCard>
        <ChartCard title="Summary" subtitle={meta.synthetic ? "Demo: stated cutoffs are the simulator's knowledge dates." : "Stated cutoffs come from models.yaml (fill in OpenAI cutoffs from the model pages)."}>
          <DataTable dense rows={rows} columns={[{ key: "model", label: "Model", render: (r) => <span className="whitespace-nowrap">{shortModel(r.model)}</span> }, { key: "cell", label: "Books", render: (r) => (r.cell === "offline" ? "offline" : "searched") }, { key: "implied_lag_months", label: "Implied lag", align: "right" }, { key: "stated_cutoff", label: "Stated cutoff", render: (r) => r.stated_cutoff ?? "–" }, { key: "stated_cutoff_lag_months", label: "Cutoff lag", align: "right", render: (r) => num(r.stated_cutoff_lag_months, 1) }, { key: "value_at_t", label: "Loading at T", align: "right", render: (r) => signed(r.value_at_t) }, { key: "peak_value", label: "Peak", align: "right", render: (r) => signed(r.peak_value) }]} />
        </ChartCard>
      </div>
    </div>
  );
}
