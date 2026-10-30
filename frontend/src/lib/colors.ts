// Heatmap ramps computed in JS so cells can carry a contrasting label colour.
type RGB = [number, number, number];
const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const css = (c: RGB) => `rgb(${Math.round(c[0])}, ${Math.round(c[1])}, ${Math.round(c[2])})`;
const lum = (c: RGB) => (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255;

const DIV = {
  light: { neg: ["#104281", "#3987e5"], mid: "#f0efec", pos: ["#e66767", "#a32f2f"] },
  dark: { neg: ["#9ec5f4", "#256abf"], mid: "#2a2a28", pos: ["#e66767", "#f3a3a3"] },
};
const SEQ = {
  light: ["#f4f8fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"],
  dark: ["#16191d", "#184f95", "#2a78d6", "#6da7ec", "#cde2fb"],
};

export function diverging(value: number | null | undefined, limit: number, dark: boolean) {
  if (value === null || value === undefined || Number.isNaN(value)) return { bg: "transparent", fg: "var(--muted)" };
  const p = dark ? DIV.dark : DIV.light;
  const t = Math.max(-1, Math.min(1, value / (limit || 1)));
  let c: RGB;
  if (t < 0) {
    const a = Math.abs(t);
    c = a < 0.5 ? mix(hex(p.mid), hex(p.neg[1]), a * 2) : mix(hex(p.neg[1]), hex(p.neg[0]), (a - 0.5) * 2);
    if (dark) c = a < 0.5 ? mix(hex(p.mid), hex(p.neg[1]), a * 2) : mix(hex(p.neg[1]), hex(p.neg[0]), (a - 0.5) * 2);
  } else {
    c = t < 0.5 ? mix(hex(p.mid), hex(p.pos[0]), t * 2) : mix(hex(p.pos[0]), hex(p.pos[1]), (t - 0.5) * 2);
  }
  return { bg: css(c), fg: lum(c) > 0.55 ? "#0b0b0b" : "#ffffff" };
}

export function sequential(value: number | null | undefined, max: number, dark: boolean) {
  if (value === null || value === undefined || Number.isNaN(value)) return { bg: "transparent", fg: "var(--muted)" };
  const stops = dark ? SEQ.dark : SEQ.light;
  const t = Math.max(0, Math.min(1, value / (max || 1))) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(t));
  const c = mix(hex(stops[i]), hex(stops[i + 1]), t - i);
  return { bg: css(c), fg: lum(c) > 0.55 ? "#0b0b0b" : "#ffffff" };
}
