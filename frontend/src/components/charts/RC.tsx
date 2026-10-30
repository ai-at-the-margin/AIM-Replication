/* Recharts wrappers that follow the dataviz mark specs: thin bars (<= 24px), 4px rounded data ends,
   2px lines, >= 8px markers, hairline grid, a legend for >= 2 series, hover tooltips everywhere. */
import React from "react";
import {
  Bar, BarChart, CartesianGrid, ErrorBar, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Cell, LabelList,
} from "recharts";
import { RechartsTip } from "./Tooltip";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Row = Record<string, any>;
export interface SeriesDef { key: string; label: string; color: string; errKey?: string }

const axisProps = { tickLine: false, axisLine: { stroke: "var(--axis)" }, tick: { fontSize: 11, fill: "var(--ink-2)" } } as const;

export function GroupedBars({ data, xKey, series, height = 300, yDomain, yFormat, refLine, layout = "horizontal", barSize = 18 }: {
  data: Row[]; xKey: string; series: SeriesDef[]; height?: number; yDomain?: [number | string, number | string];
  yFormat?: (v: number) => string; refLine?: number; layout?: "horizontal" | "vertical"; barSize?: number;
}) {
  const vertical = layout === "vertical";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={vertical ? "vertical" : "horizontal"} margin={{ top: 8, right: 16, bottom: 4, left: vertical ? 8 : 0 }} barGap={2} barCategoryGap="22%">
        <CartesianGrid vertical={vertical} horizontal={!vertical} />
        {vertical ? (
          <>
            <XAxis type="number" domain={yDomain ?? ["auto", "auto"]} tickFormatter={yFormat} {...axisProps} />
            <YAxis type="category" dataKey={xKey} width={140} {...axisProps} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...axisProps} interval={0} angle={data.length > 6 ? -35 : 0}
              textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 72 : 30} />
            <YAxis domain={yDomain ?? ["auto", "auto"]} tickFormatter={yFormat} width={48} {...axisProps} />
          </>
        )}
        <Tooltip cursor={{ fill: "rgba(127,127,127,0.08)" }} content={<RechartsTip format={(v: number) => (yFormat ? yFormat(v) : typeof v === "number" ? v.toFixed(2) : String(v))} />} />
        {series.length > 1 && <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 12 }} />}
        {refLine !== undefined && (vertical ? <ReferenceLine x={refLine} stroke="var(--axis)" /> : <ReferenceLine y={refLine} stroke="var(--axis)" />)}
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={vertical ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={barSize}>
            {s.errKey && <ErrorBar dataKey={s.errKey} width={4} strokeWidth={1.2} stroke="var(--ink-2)" direction={vertical ? "x" : "y"} />}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ColoredBars({ data, xKey, yKey, colorKey, height = 280, yFormat, label, layout = "vertical", refLine, width = 150 }: {
  data: Row[]; xKey: string; yKey: string; colorKey: string; height?: number; yFormat?: (v: number) => string;
  label?: boolean; layout?: "vertical" | "horizontal"; refLine?: number; width?: number;
}) {
  const vertical = layout === "vertical";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={vertical ? "vertical" : "horizontal"} margin={{ top: 8, right: 40, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={vertical} horizontal={!vertical} />
        {vertical ? (
          <>
            <XAxis type="number" tickFormatter={yFormat} {...axisProps} />
            <YAxis type="category" dataKey={xKey} width={width} {...axisProps} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...axisProps} />
            <YAxis tickFormatter={yFormat} width={48} {...axisProps} />
          </>
        )}
        <Tooltip cursor={{ fill: "rgba(127,127,127,0.08)" }} content={<RechartsTip format={(v: number) => (yFormat ? yFormat(v) : v.toFixed(2))} />} />
        {refLine !== undefined && (vertical ? <ReferenceLine x={refLine} stroke="var(--axis)" /> : <ReferenceLine y={refLine} stroke="var(--axis)" />)}
        <Bar dataKey={yKey} radius={vertical ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={20} name={yKey}>
          {data.map((d, i) => <Cell key={i} fill={d[colorKey]} />)}
          {label && <LabelList dataKey={yKey} position={vertical ? "right" : "top"} formatter={(v: number) => (yFormat ? yFormat(v) : v.toFixed(2))} style={{ fontSize: 11, fill: "var(--ink-2)" }} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function StackedBars({ data, xKey, series, height = 300, layout = "horizontal", percent = true, width = 120 }: {
  data: Row[]; xKey: string; series: SeriesDef[]; height?: number; layout?: "horizontal" | "vertical"; percent?: boolean; width?: number;
}) {
  const vertical = layout === "vertical";
  const fmt = (v: number) => (percent ? `${Math.round(v * 100)}%` : v.toFixed(2));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={vertical ? "vertical" : "horizontal"} margin={{ top: 8, right: 16, bottom: 4, left: 4 }} barCategoryGap="24%">
        <CartesianGrid vertical={vertical} horizontal={!vertical} />
        {vertical ? (
          <>
            <XAxis type="number" domain={percent ? [0, 1] : ["auto", "auto"]} tickFormatter={fmt} {...axisProps} />
            <YAxis type="category" dataKey={xKey} width={width} {...axisProps} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...axisProps} interval={0} angle={data.length > 8 ? -35 : 0} textAnchor={data.length > 8 ? "end" : "middle"} height={data.length > 8 ? 70 : 30} />
            <YAxis domain={percent ? [0, 1] : ["auto", "auto"]} tickFormatter={fmt} width={44} {...axisProps} />
          </>
        )}
        <Tooltip cursor={{ fill: "rgba(127,127,127,0.08)" }} content={<RechartsTip format={(v: number) => fmt(v)} />} />
        <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 11 }} />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} stroke="var(--surface)" strokeWidth={1.5} maxBarSize={vertical ? 22 : 40} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Lines({ data, xKey, series, height = 300, yFormat, refLine, xLabel, yLabel, dots = true, xType = "category" }: {
  data: Row[]; xKey: string; series: SeriesDef[]; height?: number; yFormat?: (v: number) => string; refLine?: number;
  xLabel?: string; yLabel?: string; dots?: boolean; xType?: "category" | "number";
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 24, bottom: xLabel ? 18 : 4, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={xKey} type={xType} domain={xType === "number" ? ["dataMin", "dataMax"] : undefined} {...axisProps}
          label={xLabel ? { value: xLabel, position: "insideBottom", offset: -10, fontSize: 11, fill: "var(--muted)" } : undefined} />
        <YAxis tickFormatter={yFormat} width={48} {...axisProps}
          label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--muted)" } : undefined} />
        <Tooltip content={<RechartsTip format={(v: number) => (yFormat ? yFormat(v) : typeof v === "number" ? v.toFixed(2) : String(v))} />} />
        {series.length > 1 && <Legend iconType="plainline" verticalAlign={xLabel ? "top" : "bottom"} wrapperStyle={{ fontSize: 12, paddingBottom: xLabel ? 8 : 0 }} />}
        {refLine !== undefined && <ReferenceLine y={refLine} stroke="var(--axis)" />}
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} connectNulls
            dot={dots ? { r: 4, fill: s.color, stroke: "var(--surface)", strokeWidth: 2 } : false} activeDot={{ r: 5 }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Scatterplot({ groups, height = 340, xLabel, yLabel, xKey = "x", yKey = "y", tip }: {
  groups: { name: string; color: string; points: Row[] }[]; height?: number; xLabel?: string; yLabel?: string;
  xKey?: string; yKey?: string; tip?: (p: Row) => { label: string; value: string }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: xLabel ? 20 : 4, left: 0 }}>
        <CartesianGrid />
        <XAxis type="number" dataKey={xKey} {...axisProps} domain={["auto", "auto"]}
          label={xLabel ? { value: xLabel, position: "insideBottom", offset: -10, fontSize: 11, fill: "var(--muted)" } : undefined} />
        <YAxis type="number" dataKey={yKey} width={48} {...axisProps} domain={["auto", "auto"]}
          label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--muted)" } : undefined} />
        <ZAxis range={[36, 36]} />
        <Tooltip cursor={{ strokeDasharray: "0", stroke: "var(--axis)" }}
          content={({ active, payload }: any) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload;
            const rows = tip ? tip(p) : [{ label: xKey, value: String(p[xKey]) }, { label: yKey, value: String(p[yKey]) }];
            return (
              <div className="rounded-lg border border-black/10 bg-[var(--surface)] px-3 py-2 text-xs shadow-xl dark:border-white/15">
                {rows.map((r, i) => (
                  <div key={i} className="flex justify-between gap-4"><span className="text-[var(--ink-2)]">{r.label}</span><span className="tabular font-semibold">{r.value}</span></div>
                ))}
              </div>
            );
          }} />
        {groups.length > 1 && <Legend iconType="circle" iconSize={8} verticalAlign="top" wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} />}
        {groups.map((g) => (
          <Scatter key={g.name} name={g.name} data={g.points} fill={g.color} fillOpacity={0.55} stroke="var(--surface)" strokeWidth={1} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
