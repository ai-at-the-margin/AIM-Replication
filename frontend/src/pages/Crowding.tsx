import React, { useState } from "react";
import { ChartCard, Empty } from "@/components/charts/ChartCard";
import { DataTable, Segmented, SectionTitle, StatTile } from "@/components/charts/Primitives";
import { ColoredBars, GroupedBars, StackedBars } from "@/components/charts/RC";
import { useBundle } from "@/lib/data";
import { CORE_FACTORS, FACTOR_LABEL, num, pct, sectorName, SERIES, signed } from "@/lib/format";

/* eslint-disable @typescript-eslint/no-explicit-any */
export function Crowding() {
  const { analysis } = useBundle();
  const cells: any[] = analysis.crowding?.cells ?? [];
  const [cellIdx, setCellIdx] = useState("0");
  const cell = cells[Number(cellIdx)] ?? cells[0];
  const top = (cell?.top ?? []).slice(0, 20).map((r: any) => ({ name: r.name.length > 26 ? r.name.slice(0, 25) + "…" : r.name, crowd: r.crowd_weight, universe: r.universe_weight ?? 0 }));
  const geo = analysis.geography ?? { regions: [], rows: [], universe: {} };
  const [geoStage, setGeoStage] = useState("A");
  const geoRows = (geo.rows ?? []).filter((r: any) => r.stage === geoStage).map((r: any) => ({ ...r, label: `${r.prompt_id} · ${r.provider}` }));
  geoRows.push({ label: "Universe (cap-weighted)", ...geo.universe });
  const attention: any[] = analysis.attention?.rows ?? [];
  const attRows = attention.map((r) => ({ label: `${r.prompt_id} · ${r.search_state.replace("connected_", "").replace("_", " ")}`, analyst: r.analyst_percentile, news: r.news_percentile }));
  const factorRows = CORE_FACTORS.map((f) => ({ factor: FACTOR_LABEL[f], value: cell?.exposures?.[f] ?? null, color: (cell?.exposures?.[f] ?? 0) >= 0 ? "var(--s8)" : "var(--s1)" }));
  return (
    <div>
      <SectionTitle eyebrow="New analytics" title="The AI crowd book">
        Suppose one dollar followed every valid recommendation. The aggregate book is the holdings-level picture of "AI at the margin": which names it overweights relative to the market, how concentrated it is, what it is exposed to, and where it sits geographically.
      </SectionTitle>
      {cells.length === 0 ? <Empty text="No valid books yet." /> : (
        <>
          <div className="mb-5"><Segmented id="crowd-cell" value={cellIdx} onChange={setCellIdx} size="md" options={cells.map((c, i) => ({ value: String(i), label: c.cell }))} /></div>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile><StatTile label="Books aggregated" value={cell.n_books.toLocaleString()} /></Tile>
            <Tile><StatTile label="Distinct names" value={cell.concentration?.n_names ?? "–"} sub={`${pct(cell.share_in_universe)} of weight inside the estimation universe`} /></Tile>
            <Tile><StatTile label="Effective N (crowd book)" value={num(cell.concentration?.effective_n, 1)} sub={`market: ${num(cell.universe_concentration?.effective_n, 1)}`} /></Tile>
            <Tile><StatTile label="Top-10 share" value={pct(cell.concentration?.top10_share)} sub={`market: ${pct(cell.universe_concentration?.top10_share)}`} /></Tile>
          </div>
          <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <ChartCard title="Crowd weight vs market weight, top 20 names" subtitle="Bars compare the aggregate AI book with the cap-weighted estimation universe."
              table={<DataTable dense rows={cell.top} columns={[{ key: "name", label: "Issuer" }, { key: "sector", label: "Sector", render: (r) => sectorName(r.sector) }, { key: "crowd_weight", label: "Crowd", align: "right", render: (r) => pct(r.crowd_weight, 1) }, { key: "universe_weight", label: "Market", align: "right", render: (r) => pct(r.universe_weight, 2) }, { key: "active_weight", label: "Active", align: "right", render: (r) => pct(r.active_weight, 1) }, { key: "overweight_ratio", label: "× market", align: "right", render: (r) => num(r.overweight_ratio, 1) }]} />}>
              <GroupedBars data={top} xKey="name" layout="vertical" height={Math.max(360, top.length * 26)} yFormat={(v) => pct(v, 1)} barSize={9}
                series={[{ key: "crowd", label: "AI crowd book", color: "var(--s1)" }, { key: "universe", label: "Market (cap-weighted)", color: "var(--axis)" }]} />
            </ChartCard>
            <ChartCard title="Factor exposure of the crowd book" subtitle="Weighted loadings of the aggregate book (sd units). This is the position that would show up in a factor decomposition of AI-guided flow.">
              <ColoredBars layout="horizontal" data={factorRows} xKey="factor" yKey="value" colorKey="color" refLine={0} label height={300} yFormat={(v) => signed(v)} />
            </ChartCard>
          </div>
        </>
      )}
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <ChartCard title="Where the money would go" subtitle="Regional weight of books by prompt and provider, with the cap-weighted universe as the last bar."
          actions={<Segmented id="geo-stage" value={geoStage} onChange={setGeoStage} options={[{ value: "A", label: "A" }, { value: "B", label: "B" }, { value: "C", label: "C" }]} />}>
          {geoRows.length > 1 ? <StackedBars data={geoRows} xKey="label" layout="vertical" height={Math.max(300, geoRows.length * 26 + 60)} width={170}
            series={(geo.regions ?? []).map((r: string, i: number) => ({ key: r, label: r, color: r === "Other" ? "var(--axis)" : SERIES[i] }))} /> : <Empty text="No data." />}
        </ChartCard>
        <ChartCard title="Attention and familiarity (§8.12)" subtitle="Average percentile of each pick's analyst coverage and 30-day news count within its market-cap decile. 50 is typical for the stock's size; higher means the models favour heavily covered names.">
          {attRows.length ? <GroupedBars data={attRows} xKey="label" layout="vertical" height={Math.max(300, attRows.length * 30)} yDomain={[0, 100]} barSize={9}
            series={[{ key: "analyst", label: "Analyst-count percentile", color: "var(--s3)" }, { key: "news", label: "News-count percentile", color: "var(--s7)" }]} /> : <Empty text="No attention data." />}
        </ChartCard>
      </div>
      <div className="mt-6">
        <ChartCard title="Foreign picks bought through US listings" subtitle="For non-US issuers, the share of picks written as a US listing (ADR or secondary line) rather than the home-market ticker.">
          <DataTable dense rows={geo.foreign_via_us_listing ?? []} columns={[{ key: "provider", label: "Provider" }, { key: "foreign_picks", label: "Foreign picks", align: "right" }, { key: "share_via_us_listing", label: "Via US listing", align: "right", render: (r) => pct(r.share_via_us_listing) }]} />
        </ChartCard>
      </div>
    </div>
  );
}

function Tile({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-black/10 bg-[var(--surface)] p-4 dark:border-white/10">{children}</div>;
}
