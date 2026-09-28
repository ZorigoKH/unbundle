// Number and date formatting shared by every page and chart. Inputs are decimals
// (0.012 is 1.2%); negatives get a typographic minus (U+2212), never a hyphen.

import type { FundWindow, Kind, Month } from "./types";

export const MINUS = "−";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * `x` with `digits` decimals and a typographic minus. With `sign`, positives get a "+".
 * A value that rounds to zero gets no sign at all ("0.0", never "+0.0" or "−0.0"), so a
 * rounded alpha cannot seem to disagree in sign with its t-statistic.
 */
export function fixed(x: number, digits: number, sign = false): string {
  let s = Math.abs(x).toFixed(digits);
  const zero = Number(s) === 0;
  if (zero) return s;
  if (x < 0) s = MINUS + s;
  else if (sign) s = "+" + s;
  return s;
}

/** 0.0135 -> "1.4%"; with `sign`, "+1.4%". */
export function pct(x: number, { digits = 1, sign = false } = {}): string {
  return `${fixed(100 * x, digits, sign)}%`;
}

/** Signed percent, the default for alphas and contributions: "+1.4%", "−2.1%". */
export function spct(x: number, digits = 1): string {
  return pct(x, { digits, sign: true });
}

/** An expense ratio: at least two decimals, more only when the fee has them (0.0945%). */
export function er(x: number): string {
  const p = 100 * x;
  for (const d of [2, 3, 4]) {
    if (Math.abs(Number(p.toFixed(d)) - p) < 1e-9) return `${fixed(p, d)}%`;
  }
  return `${fixed(p, 4)}%`;
}

/** A t-statistic: "1.03", "−2.60". */
export function tstat(x: number): string {
  return fixed(x, 2);
}

/** A plain decimal with a typographic minus: betas, R², ratios. */
export function dec(x: number, digits = 2, sign = false): string {
  return fixed(x, digits, sign);
}

/** A p-value: "0.31", "< 0.001". */
export function pval(p: number): string {
  return p < 0.001 ? "< 0.001" : p.toFixed(p < 0.01 ? 3 : 2);
}

/** Growth of $1: "$3.95". */
export function dollars(x: number): string {
  return `$${x.toFixed(2)}`;
}

/** A share of return as a whole percent: 0.912 -> "91%"; null -> "—". */
export function share(x: number | null): string {
  return x === null ? "—" : `${fixed(100 * x, 0)}%`;
}

/** "2026-08" -> "Aug 2026" */
export function month(m: Month): string {
  const [y, mm] = m.split("-");
  return `${MONTHS[Number(mm) - 1] ?? mm} ${y}`;
}

/** "2026-08" -> 24319, a month count that subtracts cleanly. */
export function monthIndex(m: Month): number {
  return Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - 1;
}

/** "Sep 2016 – Aug 2026 · 120 months" */
export function windowLabel(w: FundWindow): string {
  return `${month(w.start)} – ${month(w.end)} · ${w.months} months`;
}

/**
 * Window length in years, one decimal, halves rounded up: 75 months -> "6.3". Integer
 * arithmetic, exactly as `years()` in live/summarize.py writes it into the verdicts.
 */
export function years(months: number): string {
  const tenths = Math.floor((10 * months + 6) / 12);
  return `${Math.floor(tenths / 10)}.${tenths % 10}`;
}

/** "2026-02-28" -> "28 Feb 2026" */
export function date(d: string): string {
  const [y, m, day] = d.split("-");
  return `${Number(day)} ${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

export const KIND_LABELS: Record<Kind, string> = {
  "active-fund": "active fund",
  "active-etf": "active ETF",
  company: "company",
  "factor-fund": "factor fund",
  "index-fund": "index fund",
  "sector-fund": "sector fund",
};

export const KIND_PLURALS: Record<Kind, string> = {
  "active-fund": "active funds",
  "active-etf": "active ETFs",
  company: "companies",
  "factor-fund": "factor funds",
  "index-fund": "index funds",
  "sector-fund": "sector funds",
};

/** Kinds whose returns are meant to track factors, so alpha is not the point. */
export const PASSIVE_KINDS: readonly Kind[] = ["factor-fund", "index-fund", "sector-fund"];

/** Lowercase factor names, matching unbundle.FACTOR_LABELS. */
export const FACTOR_LABELS: Record<string, string> = {
  MktRF: "market",
  SMB: "size",
  HML: "value",
  RMW: "profitability",
  CMA: "investment",
  Mom: "momentum",
  alpha: "alpha",
};

export function factorLabel(f: string): string {
  return FACTOR_LABELS[f] ?? f;
}

export const MODEL_LABELS: Record<string, string> = {
  capm: "CAPM",
  ff3: "Fama–French three-factor",
  carhart: "Carhart four-factor",
  ff5: "Fama–French five-factor",
  ff5mom: "Fama–French five-factor + momentum",
};

export function modelLabel(m: string): string {
  return MODEL_LABELS[m] ?? m;
}

/** An axis tick in percent with as few decimals as it needs: 0.05 -> "5%", 0.025 -> "2.5%". */
export function tickPct(x: number): string {
  const p = Math.round(100 * x * 100) / 100;
  const digits = Number.isInteger(p) ? 0 : Number.isInteger(Math.round(p * 10 * 1e6) / 1e6) ? 1 : 2;
  return `${fixed(p, digits)}%`;
}

/** An axis tick for a plain number with as few decimals as it needs. */
export function tickNum(x: number): string {
  const r = Math.round(x * 100) / 100;
  const digits = Number.isInteger(r) ? 0 : Number.isInteger(Math.round(r * 10 * 1e6) / 1e6) ? 1 : 2;
  return fixed(r, digits);
}

/** True when `x` shows as a positive percent at `digits` decimals (so "0.0%" is not). */
export function showsPositive(x: number, digits = 1): boolean {
  return Number((100 * x).toFixed(digits)) > 0;
}
