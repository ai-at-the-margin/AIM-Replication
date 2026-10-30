import React from "react";
import { TipBox, useFloatingTip } from "./Tooltip";

export interface DumbbellRow { label: string; before: number | null; after: number | null; note?: string; color?: string }

export function Dumbbell({ rows, domain, xLabel, beforeLabel = "search off", afterLabel = "search available" }: {
  rows: DumbbellRow[]; domain?: [number, number]; xLabel?: string; beforeLabel?: string; afterLabel?: string;
}) {
  const { setTip, layer } = useFloatingTip();
  let lo = -0.5, hi = 0.5;
  for (const r of rows) for (const v of [r.before, r.after]) if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const [d0, d1] = domain ?? [Math.floor(lo * 4) / 4 - 0.05, Math.ceil(hi * 4) / 4 + 0.05];
  const W = 640, rowH = 40, left = 150, right = 110, top = 18;
  const H = top + rows.length * rowH + (xLabel ? 46 : 30);
  const x = (v: number) => left + ((v - d0) / (d1 - d0)) * (W - left - right);
  const ticks: number[] = [];
  const step = (d1 - d0) > 1.5 ? 0.5 : 0.25;
  for (let t = Math.ceil(d0 / step) * step; t <= d1 + 1e-9; t += step) ticks.push(Number(t.toFixed(2)));
  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="dumbbell chart">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 6} y2={top + rows.length * rowH + 4} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={t === 0 ? 1.2 : 1} />
            <text x={x(t)} y={top + rows.length * rowH + 20} textAnchor="middle" fontSize="11" fill="var(--ink-2)" className="tabular">{t.toFixed(2)}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = top + i * rowH + rowH / 2;
          const color = r.color ?? "var(--s1)";
          return (
            <g key={r.label}
               onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, node: <TipBox title={r.label} rows={[
                 { label: beforeLabel, value: r.before === null ? "–" : r.before.toFixed(2) },
                 { label: afterLabel, value: r.after === null ? "–" : r.after.toFixed(2), color },
                 ...(r.note ? [{ label: "note", value: r.note }] : []),
               ]} /> })}
               onMouseLeave={() => setTip(null)}>
              <rect x={0} y={y - rowH / 2} width={W} height={rowH} fill="transparent" />
              <text x={left - 12} y={y + 4} textAnchor="end" fontSize="12" fill="var(--ink)">{r.label}</text>
              {r.before !== null && r.after !== null && Math.abs(x(r.after) - x(r.before)) > 10 && (
                <line x1={x(r.before)} x2={x(r.after) + (r.after > r.before ? -7 : 7)} y1={y} y2={y} stroke={color} strokeWidth={2.5} markerEnd="url(#arrow)" />
              )}
              {r.before !== null && <circle cx={x(r.before)} cy={y} r={5.5} fill="var(--ink)" stroke="var(--surface)" strokeWidth={2} />}
              {r.after !== null && <circle cx={x(r.after)} cy={y} r={6.5} fill="var(--surface)" stroke={color} strokeWidth={2.5} />}
              {r.note && <text x={W - right + 12} y={y + 4} fontSize="11" fill="var(--muted)">{r.note}</text>}
            </g>
          );
        })}
        {xLabel && <text x={(left + W - right) / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="var(--muted)">{xLabel}</text>}
      </svg>
      <div className="mt-1 flex gap-4 text-[11px] text-[var(--ink-2)]">
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--ink)]" /> {beforeLabel}</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-[var(--s1)]" /> {afterLabel}</span>
      </div>
      {layer}
    </div>
  );
}
