// Minimal scales and tick pickers for the hand-written SVG charts.

export type Scale = (v: number) => number;

/** Maps [d0, d1] onto [r0, r1] linearly. */
export function linear([d0, d1]: [number, number], [r0, r1]: [number, number]): Scale {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  // Rounded to 1/100 px: server and browser Math.log differ in the last digit, and unrounded
  // coordinates would make the pre-rendered SVG mismatch on hydration.
  return (v) => Math.round((r0 + (v - d0) * k) * 100) / 100;
}

/** Maps [d0, d1] (both > 0) onto [r0, r1] on a log axis. */
export function log([d0, d1]: [number, number], [r0, r1]: [number, number]): Scale {
  const s = linear([Math.log(d0), Math.log(d1)], [r0, r1]);
  return (v) => s(Math.log(v));
}

/** A 1-2-5 step that gives about `count` ticks across [lo, hi]. */
export function niceStep(lo: number, hi: number, count: number): number {
  const raw = (hi - lo) / Math.max(1, count);
  if (!(raw > 0)) return 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const n = raw / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

/** Round tick values covering [lo, hi], and the widened domain they span. */
export function niceTicks(
  lo: number,
  hi: number,
  count = 5,
): { ticks: number[]; domain: [number, number] } {
  if (lo === hi) {
    lo -= 0.5;
    hi += 0.5;
  }
  const step = niceStep(lo, hi, count);
  const start = Math.floor(lo / step + 1e-9) * step;
  const end = Math.ceil(hi / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { ticks, domain: [start, end] };
}

const LOG_CANDIDATES = [
  0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 0.8, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15,
  20, 25, 30, 40, 50, 60, 80, 100,
];

/** Readable ticks for a growth-of-$1 log axis: always 1, at most `max` values. */
export function logTicks(lo: number, hi: number, max = 6): number[] {
  const inside = LOG_CANDIDATES.filter((v) => v >= lo && v <= hi);
  if (inside.length <= max) return inside;
  // Keep ticks roughly evenly spaced in log terms, anchored at 1.
  const target = (Math.log(hi) - Math.log(lo)) / (max - 1);
  const out = [1];
  let last = Math.log(1);
  for (const v of inside.filter((v) => v > 1)) {
    if (Math.log(v) - last >= target * 0.8) {
      out.push(v);
      last = Math.log(v);
    }
  }
  last = 0;
  for (const v of inside.filter((v) => v < 1).reverse()) {
    if (last - Math.log(v) >= target * 0.8) {
      out.unshift(v);
      last = Math.log(v);
    }
  }
  return out;
}

/** Evenly spread vertical label positions: nudges `ys` apart by at least `gap`. */
export function spread(ys: number[], gap: number, lo: number, hi: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const placed = order.map((o) => o.y);
  for (let k = 1; k < placed.length; k++) {
    placed[k] = Math.max(placed[k]!, placed[k - 1]! + gap);
  }
  const last = placed.length - 1;
  if (last >= 0 && placed[last]! > hi) {
    placed[last] = hi;
    for (let k = last - 1; k >= 0; k--) placed[k] = Math.min(placed[k]!, placed[k + 1]! - gap);
  }
  if (last >= 0 && placed[0]! < lo) placed[0] = lo;
  const out = new Array<number>(ys.length);
  order.forEach((o, k) => (out[o.i] = placed[k]!));
  return out;
}

/** An SVG polyline path through the points, skipping none. */
export function linePath(xs: number[], ys: number[]): string {
  let d = "";
  for (let i = 0; i < xs.length; i++) {
    d += `${i === 0 ? "M" : "L"}${xs[i]!.toFixed(1)},${ys[i]!.toFixed(1)}`;
  }
  return d;
}

/**
 * January month indices (year * 12) between `m0` and `m1` (month indices), stepping whole
 * years so that at most `max` ticks appear.
 */
export function yearTicks(m0: number, m1: number, max: number): number[] {
  const y0 = Math.ceil(m0 / 12);
  const y1 = Math.floor(m1 / 12);
  const span = y1 - y0;
  if (span < 0) return [];
  const step = [1, 2, 5, 10, 20].find((s) => Math.floor(span / s) + 1 <= Math.max(1, max)) ?? 25;
  const first = Math.ceil(y0 / step) * step;
  const out: number[] = [];
  for (let y = first; y <= y1; y += step) out.push(y * 12);
  return out;
}
