// Reads web/data at build time (server components only) and checks every file against the
// schema in lib/types.ts. Any missing or ill-typed field throws, so `next build` fails on bad
// data instead of publishing a broken page.

import fs from "node:fs";
import path from "node:path";

import {
  type Fund,
  type FundSummary,
  type Index,
  KINDS,
  type Meta,
  ROLLING_FACTORS,
  VERDICTS,
} from "./types";

export type * from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const DATE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
const TICKER = /^[A-Z0-9][A-Z0-9.-]*$/; // same rule as live/__init__.py; also a safe path
const SUM_TOLERANCE = 1e-6; // contributions vs excess_annual, after 6-decimal rounding

class DataError extends Error {
  constructor(where: string, problem: string) {
    super(`web/data: ${where}: ${problem}`);
    this.name = "DataError";
  }
}

// -- field checks ------------------------------------------------------------------------
type Obj = Record<string, unknown>;

function obj(x: unknown, where: string): Obj {
  if (typeof x !== "object" || x === null || Array.isArray(x)) {
    throw new DataError(where, "expected an object");
  }
  return x as Obj;
}

function field(o: Obj, key: string, where: string): unknown {
  if (!(key in o)) throw new DataError(where, `missing field "${key}"`);
  return o[key];
}

function num(o: Obj, key: string, where: string): number {
  const v = field(o, key, where);
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new DataError(`${where}.${key}`, `expected a finite number, got ${JSON.stringify(v)}`);
  }
  return v;
}

function int(o: Obj, key: string, where: string): number {
  const v = num(o, key, where);
  if (!Number.isInteger(v)) throw new DataError(`${where}.${key}`, "expected an integer");
  return v;
}

function numOrNull(o: Obj, key: string, where: string): number | null {
  return field(o, key, where) === null ? null : num(o, key, where);
}

function str(o: Obj, key: string, where: string, pattern?: RegExp): string {
  const v = field(o, key, where);
  if (typeof v !== "string") throw new DataError(`${where}.${key}`, "expected a string");
  if (pattern && !pattern.test(v)) {
    throw new DataError(`${where}.${key}`, `${JSON.stringify(v)} does not match ${pattern}`);
  }
  return v;
}

function bool(o: Obj, key: string, where: string): boolean {
  const v = field(o, key, where);
  if (typeof v !== "boolean") throw new DataError(`${where}.${key}`, "expected a boolean");
  return v;
}

function oneOf<T extends string>(o: Obj, key: string, allowed: readonly T[], where: string): T {
  const v = str(o, key, where);
  if (!(allowed as readonly string[]).includes(v)) {
    throw new DataError(`${where}.${key}`, `${JSON.stringify(v)} is not one of ${allowed}`);
  }
  return v as T;
}

function list(o: Obj, key: string, where: string): unknown[] {
  const v = field(o, key, where);
  if (!Array.isArray(v)) throw new DataError(`${where}.${key}`, "expected an array");
  return v;
}

function numbers(o: Obj, key: string, where: string): number[] {
  return list(o, key, where).map((v, i) => {
    if (typeof v !== "number" || !Number.isFinite(v)) {
      throw new DataError(`${where}.${key}[${i}]`, "expected a finite number");
    }
    return v;
  });
}

function strings(o: Obj, key: string, where: string, pattern?: RegExp): string[] {
  return list(o, key, where).map((v, i) => {
    if (typeof v !== "string" || (pattern && !pattern.test(v))) {
      throw new DataError(`${where}.${key}[${i}]`, `unexpected value ${JSON.stringify(v)}`);
    }
    return v;
  });
}

function stringMap(o: Obj, key: string, where: string): Record<string, string> {
  const m = obj(field(o, key, where), `${where}.${key}`);
  for (const [k, v] of Object.entries(m)) {
    if (typeof v !== "string") throw new DataError(`${where}.${key}.${k}`, "expected a string");
  }
  return m as Record<string, string>;
}

function numberMap(o: Obj, key: string, where: string): Record<string, number> {
  const m = obj(field(o, key, where), `${where}.${key}`);
  for (const k of Object.keys(m)) num(m, k, `${where}.${key}`);
  return m as Record<string, number>;
}

function sameLength(where: string, n: number, arrays: Record<string, unknown[]>): void {
  for (const [name, a] of Object.entries(arrays)) {
    if (a.length !== n) {
      throw new DataError(where, `${name} has ${a.length} entries, expected ${n}`);
    }
  }
}

function monthIndex(m: string): number {
  return Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - 1;
}

// -- record checks -----------------------------------------------------------------------
export function assertMeta(x: unknown, where = "meta.json"): asserts x is Meta {
  const o = obj(x, where);
  int(o, "schema_version", where);
  str(o, "generated_at", where, DATE);
  str(o, "through", where, MONTH);
  str(o, "factors_through", where, MONTH);
  str(o, "headline_model", where);
  str(o, "robustness_model", where);
  int(o, "window_months", where);
  int(o, "min_months", where);
  int(o, "rolling_window", where);
  int(o, "funds", where);
  strings(o, "stale", where, TICKER);
  strings(o, "excluded", where, TICKER);
  stringMap(o, "sources", where);
  stringMap(o, "versions", where);
}

export function assertSummary(x: unknown, where: string): asserts x is FundSummary {
  const o = obj(x, where);
  str(o, "ticker", where, TICKER);
  str(o, "name", where);
  oneOf(o, "kind", KINDS, where);
  str(o, "category", where);
  num(o, "expense_ratio", where);
  const w = obj(field(o, "window", where), `${where}.window`);
  const start = str(w, "start", `${where}.window`, MONTH);
  const end = str(w, "end", `${where}.window`, MONTH);
  const months = int(w, "months", `${where}.window`);
  if (monthIndex(end) - monthIndex(start) + 1 !== months) {
    throw new DataError(`${where}.window`, `${start} to ${end} is not ${months} months`);
  }
  bool(o, "short_history", where);
  bool(o, "stale", where);
  num(o, "excess_annual", where);
  num(o, "alpha_annual", where);
  num(o, "alpha_t", where);
  num(o, "alpha_p", where);
  num(o, "r2", where);
  numOrNull(o, "factor_share", where);
  oneOf(o, "verdict_short", VERDICTS, where);
}

function assertModelFit(x: unknown, where: string): void {
  const o = obj(x, where);
  str(o, "model", where);
  const factors = strings(o, "factors", where);
  int(o, "nobs", where);
  int(o, "maxlags", where);
  for (const k of ["alpha_annual", "alpha_se_annual", "alpha_t", "alpha_p", "excess_annual"]) {
    num(o, k, where);
  }
  for (const k of ["r2", "r2_adj", "tracking_error", "information_ratio"]) num(o, k, where);

  const betas = obj(field(o, "betas", where), `${where}.betas`);
  const premia = numberMap(o, "premia", where);
  const contributions = numberMap(o, "contributions", where);
  for (const f of factors) {
    const b = obj(field(betas, f, `${where}.betas`), `${where}.betas.${f}`);
    for (const k of ["coef", "se", "t"]) num(b, k, `${where}.betas.${f}`);
    num(premia, f, `${where}.premia`);
    num(contributions, f, `${where}.contributions`);
  }
  num(contributions, "alpha", `${where}.contributions`);
  const total = Object.values(contributions).reduce((a, b) => a + b, 0);
  if (Math.abs(total - (o.excess_annual as number)) > SUM_TOLERANCE) {
    throw new DataError(`${where}.contributions`, `sum ${total} != excess_annual`);
  }
}

export function assertFund(x: unknown, where: string): asserts x is Fund {
  assertSummary(x, where);
  const o = x as unknown as Obj;
  int(o, "schema_version", where);
  str(o, "expense_ratio_as_of", where);
  str(o, "expense_ratio_source", where);
  str(o, "note", where);
  str(o, "verdict", where);

  const models = obj(field(o, "models", where), `${where}.models`);
  assertModelFit(field(models, "carhart", `${where}.models`), `${where}.models.carhart`);
  assertModelFit(field(models, "ff5mom", `${where}.models`), `${where}.models.ff5mom`);

  const fee = obj(field(o, "fee", where), `${where}.fee`);
  for (const k of ["expense_ratio", "alpha_net", "alpha_gross", "breakeven_fee"]) {
    num(fee, k, `${where}.fee`);
  }
  const ci = numbers(fee, "alpha_ci95", `${where}.fee`);
  if (ci.length !== 2 || ci[0]! > ci[1]!) {
    throw new DataError(`${where}.fee.alpha_ci95`, "expected [lo, hi] with lo <= hi");
  }

  const g = obj(field(o, "growth", where), `${where}.growth`);
  const gw = `${where}.growth`;
  const gMonths = strings(g, "months", gw, MONTH);
  sameLength(gw, x.window.months + 1, {
    months: gMonths,
    fund: numbers(g, "fund", gw),
    replica: numbers(g, "replica", gw),
    tbills: numbers(g, "tbills", gw),
  });

  const r = obj(field(o, "rolling", where), `${where}.rolling`);
  const rw = `${where}.rolling`;
  int(r, "window", rw);
  const rMonths = strings(r, "months", rw, MONTH);
  const rBetas = obj(field(r, "betas", rw), `${rw}.betas`);
  const series: Record<string, unknown[]> = {
    alpha_annual: numbers(r, "alpha_annual", rw),
    r2: numbers(r, "r2", rw),
  };
  for (const f of ROLLING_FACTORS) series[`betas.${f}`] = numbers(rBetas, f, `${rw}.betas`);
  sameLength(rw, rMonths.length, series);
}

// -- loading -----------------------------------------------------------------------------
function readJson(rel: string): unknown {
  const file = path.join(DATA_DIR, rel);
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (err) {
    throw new DataError(rel, `cannot read (${(err as Error).message})`);
  }
}

let meta: Meta | undefined;
let index: Index | undefined;
const funds = new Map<string, Fund>();

export function getMeta(): Meta {
  if (!meta) {
    const x = readJson("meta.json");
    assertMeta(x);
    meta = x;
  }
  return meta;
}

export function getIndex(): Index {
  if (!index) {
    const o = obj(readJson("index.json"), "index.json");
    const through = str(o, "through", "index.json", MONTH);
    const rows = list(o, "funds", "index.json");
    rows.forEach((row, i) => assertSummary(row, `index.json.funds[${i}]`));
    const summaries = rows as FundSummary[];

    const m = getMeta();
    if (through !== m.through) {
      throw new DataError("index.json.through", `${through} != meta.json through ${m.through}`);
    }
    if (summaries.length !== m.funds) {
      throw new DataError("index.json.funds", `${summaries.length} funds, meta says ${m.funds}`);
    }
    const tickers = new Set(summaries.map((s) => s.ticker));
    if (tickers.size !== summaries.length) {
      throw new DataError("index.json.funds", "duplicate tickers");
    }
    index = { through, funds: summaries };
  }
  return index;
}

export function getTickers(): string[] {
  return getIndex().funds.map((f) => f.ticker);
}

export function getFund(ticker: string): Fund {
  const cached = funds.get(ticker);
  if (cached) return cached;
  if (!getTickers().includes(ticker)) throw new DataError(ticker, "not in index.json");
  const where = `funds/${ticker}.json`;
  const x = readJson(where);
  assertFund(x, where);
  if (x.ticker !== ticker) throw new DataError(`${where}.ticker`, `expected ${ticker}`);
  funds.set(ticker, x);
  return x;
}
