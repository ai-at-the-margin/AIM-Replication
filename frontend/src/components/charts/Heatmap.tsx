import React from "react";
import { diverging, sequential } from "@/lib/colors";
import { useData } from "@/lib/data";
import { TipBox, useFloatingTip } from "./Tooltip";

export function Heatmap({
  rows, cols, values, mode = "diverging", limit, max = 1, format = (v) => v.toFixed(2), boxed, rowLabel, colLabel,
  highlightLastRow, cellHeight = 34, divider,
}: {
  rows: string[];
  cols: string[];
  values: (number | null)[][];
  mode?: "diverging" | "sequential";
  limit?: number;
  max?: number;
  format?: (v: number) => string;
  boxed?: Set<string>;
  rowLabel?: (r: string) => React.ReactNode;
  colLabel?: (c: string) => React.ReactNode;
  highlightLastRow?: boolean;
  cellHeight?: number;
  divider?: number;
}) {
  const { dark } = useData();
  const { setTip, layer } = useFloatingTip();
  let auto = 0.5;
  for (const row of values) for (const v of row) if (v !== null && Math.abs(v) > auto) auto = Math.abs(v);
  const lim = limit ?? auto;
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-separate border-spacing-[2px] text-xs">
        <thead>
          <tr>
            <th />
            {cols.map((c, j) => (
              <th key={c} className={"px-1 pb-1 text-center font-medium text-[var(--ink-2)] " + (divider === j ? "border-l-2 border-[var(--ink)]" : "")}>
                {colLabel ? colLabel(c) : c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r} className={highlightLastRow && i === rows.length - 1 ? "font-semibold" : ""}>
              <td className="whitespace-nowrap pr-2 text-right text-[var(--ink-2)]" style={{ height: cellHeight }}>
                {rowLabel ? rowLabel(r) : r}
              </td>
              {cols.map((c, j) => {
                const v = values[i]?.[j] ?? null;
                const color = mode === "diverging" ? diverging(v, lim, dark) : sequential(v, max, dark);
                const isBoxed = boxed?.has(`${r}|${c}`);
                return (
                  <td
                    key={c}
                    tabIndex={0}
                    onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, node: <TipBox title={`${r} · ${c}`} rows={[{ label: "value", value: v === null ? "–" : format(v) }]} /> })}
                    onMouseLeave={() => setTip(null)}
                    className={"tabular rounded-[4px] text-center transition-[filter] hover:brightness-110 " + (divider === j ? "border-l-2 border-[var(--ink)]" : "")}
                    style={{ background: color.bg, color: color.fg, outline: isBoxed ? "2px solid var(--ink)" : undefined, outlineOffset: -2, minWidth: 44 }}
                  >
                    {v === null ? "" : format(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {layer}
    </div>
  );
}
