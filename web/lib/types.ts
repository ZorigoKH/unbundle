// Types for the JSON that `python -m live.build` writes to web/data. They mirror the schema
// exactly: every number is a decimal (0.012 is 1.2%), per year where the name says
// "annual", and months are "YYYY-MM". lib/data.ts checks each file against these at build.

export const KINDS = [
  "active-fund",
  "active-etf",
  "company",
  "factor-fund",
  "index-fund",
  "sector-fund",
] as const;
export type Kind = (typeof KINDS)[number];

export const VERDICTS = [
  "skill",
  "trails its factors",
  "no detectable alpha",
  "as designed",
] as const;
export type VerdictShort = (typeof VERDICTS)[number];

/** "YYYY-MM" */
export type Month = string;

export type Meta = {
  schema_version: number;
  generated_at: string;
  through: Month;
  factors_through: Month;
  headline_model: string;
  robustness_model: string;
  window_months: number;
  min_months: number;
  rolling_window: number;
  funds: number;
  stale: string[];
  excluded: string[];
  sources: Record<string, string>;
  versions: Record<string, string>;
};

export type FundWindow = {
  start: Month;
  end: Month;
  months: number;
};

export type FundSummary = {
  ticker: string;
  name: string;
  kind: Kind;
  category: string;
  expense_ratio: number;
  window: FundWindow;
  short_history: boolean;
  stale: boolean;
  excess_annual: number;
  alpha_annual: number;
  alpha_t: number;
  alpha_p: number;
  r2: number;
  /** 1 - alpha_annual / excess_annual when excess_annual > 0.01; null otherwise. */
  factor_share: number | null;
  verdict_short: VerdictShort;
};

export type Index = {
  through: Month;
  funds: FundSummary[];
};

export type Beta = {
  coef: number;
  se: number;
  t: number;
};

export type ModelFit = {
  model: string;
  factors: string[];
  nobs: number;
  maxlags: number;
  alpha_annual: number;
  alpha_se_annual: number;
  alpha_t: number;
  alpha_p: number;
  betas: Record<string, Beta>;
  premia: Record<string, number>;
  /** One entry per factor plus "alpha"; they sum to excess_annual. */
  contributions: Record<string, number>;
  excess_annual: number;
  r2: number;
  r2_adj: number;
  tracking_error: number;
  information_ratio: number;
};

export type Fee = {
  expense_ratio: number;
  alpha_net: number;
  alpha_gross: number;
  alpha_ci95: [number, number];
  breakeven_fee: number;
};

export type Growth = {
  months: Month[];
  fund: number[];
  replica: number[];
  tbills: number[];
};

export const ROLLING_FACTORS = ["MktRF", "SMB", "HML", "Mom"] as const;
export type RollingFactor = (typeof ROLLING_FACTORS)[number];

export type Rolling = {
  window: number;
  months: Month[];
  alpha_annual: number[];
  betas: Record<RollingFactor, number[]>;
  r2: number[];
};

export type Fund = FundSummary & {
  schema_version: number;
  expense_ratio_as_of: string;
  expense_ratio_source: string;
  note: string;
  verdict: string;
  models: { carhart: ModelFit; ff5mom: ModelFit };
  fee: Fee;
  growth: Growth;
  rolling: Rolling;
};
