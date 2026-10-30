export const FACTOR_LABEL: Record<string, string> = {
  size: "Size", value: "Value", quality: "Quality", momentum: "Momentum", lowvol: "Low-Vol",
  resvol: "ResVol", beta: "Beta", mom_12_1: "Mom 12-1", value_blend: "Value (blend)",
};
export const CORE_FACTORS = ["value", "momentum", "quality", "size", "lowvol", "beta"];
export const FREEFORM = ["L1", "L2", "L3", "L4"];
export const MANDATES = ["VALUE", "QUALITY", "MOMENTUM", "UNCONSTRAINED"];
export const PROMPT_LABEL: Record<string, string> = {
  L1: "L1 bare request", L2: "L2 amount & weights", L3: "L3 investor profile", L4: "L4 fund-manager brief",
  VALUE: "Value", QUALITY: "Quality", MOMENTUM: "Momentum", UNCONSTRAINED: "Unconstrained",
};
export const SECTOR: Record<string, string> = {
  "10": "Energy", "15": "Materials", "20": "Industrials", "25": "Cons. Discretionary", "30": "Cons. Staples",
  "35": "Health Care", "40": "Financials", "45": "Info. Technology", "50": "Comm. Services", "55": "Utilities",
  "60": "Real Estate",
};
export const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"];
export const PROVIDER_COLOR: Record<string, string> = { openai: "var(--openai)", anthropic: "var(--anthropic)" };

export function num(v: unknown, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  return Number(v).toFixed(digits);
}
export function signed(v: unknown, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  const n = Number(v);
  return (n > 0 ? "+" : n < 0 ? "−" : "") + Math.abs(n).toFixed(digits);
}
export function pct(v: unknown, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  return (Number(v) * 100).toFixed(digits) + "%";
}
export function usd(v: unknown, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  const n = Number(v);
  if (Math.abs(n) >= 1000) return "$" + (n / 1000).toFixed(1) + "K";
  return "$" + n.toFixed(digits);
}
export function compact(v: unknown): string {
  if (v === null || v === undefined) return "–";
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(1) + "K";
  return n.toLocaleString();
}
export function shortModel(id: string): string {
  return id.replace("claude-", "").replace("gpt-", "gpt-");
}
export function sectorName(code: unknown): string {
  const key = String(code ?? "").split(".")[0];
  return SECTOR[key] ?? (key || "Unknown");
}
