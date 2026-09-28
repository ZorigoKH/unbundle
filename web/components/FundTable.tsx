"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  KIND_LABELS,
  KIND_PLURALS,
  dec,
  er,
  share,
  showsPositive,
  spct,
  tstat,
} from "@/lib/format";
import { type FundSummary, KINDS, type Kind } from "@/lib/types";

type Key = "default" | "ticker" | "kind" | "er" | "alpha" | "t" | "r2" | "share";
type Dir = "asc" | "desc";

type Column = {
  key: Key;
  label: string;
  numeric: boolean;
  value: (f: FundSummary) => number | string | null;
};

const COLUMNS: Column[] = [
  { key: "ticker", label: "fund", numeric: false, value: (f) => f.ticker },
  { key: "kind", label: "kind", numeric: false, value: (f) => KINDS.indexOf(f.kind) },
  { key: "er", label: "expense ratio", numeric: true, value: (f) => f.expense_ratio },
  { key: "alpha", label: "alpha after fees", numeric: true, value: (f) => f.alpha_annual },
  { key: "t", label: "t", numeric: true, value: (f) => f.alpha_t },
  { key: "r2", label: "R²", numeric: true, value: (f) => f.r2 },
  { key: "share", label: "factor share", numeric: true, value: (f) => f.factor_share },
];

function compare(a: number | string | null, b: number | string | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1; // nulls last in either direction (handled by caller)
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

/**
 * The fund table: sortable by any column, filterable by kind. Rows arrive in the index's
 * order (kind, then ticker), which is also the "default" sort.
 */
export function FundTable({ funds }: { funds: FundSummary[] }) {
  const [kind, setKind] = useState<Kind | "all">("all");
  const [sort, setSort] = useState<{ key: Key; dir: Dir }>({ key: "default", dir: "asc" });

  const counts = useMemo(() => {
    const c = new Map<Kind, number>();
    for (const f of funds) c.set(f.kind, (c.get(f.kind) ?? 0) + 1);
    return c;
  }, [funds]);

  const rows = useMemo(() => {
    const shown = kind === "all" ? [...funds] : funds.filter((f) => f.kind === kind);
    const col = COLUMNS.find((c) => c.key === sort.key);
    if (!col) return shown;
    const sign = sort.dir === "asc" ? 1 : -1;
    return shown.sort((a, b) => {
      const va = col.value(a);
      const vb = col.value(b);
      if (va === null || vb === null) return compare(va, vb);
      return sign * compare(va, vb) || a.ticker.localeCompare(b.ticker);
    });
  }, [funds, kind, sort]);

  function toggle(col: Column) {
    setSort((s) => {
      if (s.key !== col.key) return { key: col.key, dir: col.numeric ? "desc" : "asc" };
      const first: Dir = col.numeric ? "desc" : "asc";
      // Third click returns to the default order.
      if (s.dir !== first) return { key: "default", dir: "asc" };
      return { key: col.key, dir: first === "asc" ? "desc" : "asc" };
    });
  }

  const filters: (Kind | "all")[] = ["all", ...KINDS.filter((k) => counts.has(k))];

  return (
    <div>
      <div role="group" aria-label="filter by kind" className="mb-4 flex flex-wrap gap-2 text-sm">
        {filters.map((k) => {
          const on = k === kind;
          const n = k === "all" ? funds.length : (counts.get(k) ?? 0);
          const text = k === "all" ? "all" : n === 1 ? KIND_LABELS[k] : KIND_PLURALS[k];
          return (
            <button
              key={k}
              type="button"
              aria-pressed={on}
              onClick={() => setKind(k)}
              className={`border px-2.5 py-1 transition-colors ${
                on
                  ? "border-fg bg-fg text-bg"
                  : "border-line text-muted hover:border-fg hover:text-fg"
              }`}
            >
              {text} <span className="num opacity-70">{n}</span>
            </button>
          );
        })}
      </div>

      <div className="table-scroll border-y border-line">
        <table className="w-full min-w-[34rem] border-collapse text-sm sm:min-w-[46rem]">
          <caption className="sr-only">
            Carhart four-factor alpha after fees for each fund over its headline window. Column
            headers sort the table.
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              {COLUMNS.map((c) => {
                const on = sort.key === c.key;
                const aria = on ? (sort.dir === "asc" ? "ascending" : "descending") : undefined;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={aria}
                    className={`px-2 py-2 font-normal first:pl-0 last:pr-0 ${
                      c.numeric ? "text-right" : ""
                    } ${c.key === "kind" ? "hidden sm:table-cell" : ""} ${
                      c.key === "ticker" ? "sticky left-0 z-[1] bg-bg sm:static" : ""
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => toggle(c)}
                      className={`inline-flex items-center gap-1 whitespace-nowrap hover:text-fg ${
                        on ? "text-fg" : ""
                      }`}
                    >
                      {c.label}
                      <span aria-hidden="true" className="inline-block w-2">
                        {on ? (sort.dir === "asc" ? "↑" : "↓") : ""}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.ticker} className="group border-b border-line last:border-b-0 hover:bg-band">
                <th
                  scope="row"
                  className="sticky left-0 z-[1] bg-bg py-2.5 pr-2 text-left align-top font-normal group-hover:bg-band sm:static sm:bg-transparent"
                >
                  <Link href={`/fund/${f.ticker}`} className="font-medium">
                    {f.ticker}
                  </Link>
                  {f.short_history && (
                    <span className="ml-2 text-xs text-muted">short history</span>
                  )}
                  {f.stale && <span className="ml-2 text-xs text-muted">stale</span>}
                  <div className="max-w-[9.5rem] text-xs text-muted sm:max-w-[20rem]">{f.name}</div>
                </th>
                <td className="hidden px-2 py-2.5 align-top whitespace-nowrap text-muted sm:table-cell">
                  {KIND_LABELS[f.kind]}
                </td>
                <td className="num px-2 py-2.5 text-right align-top">{er(f.expense_ratio)}</td>
                <td
                  className={`num px-2 py-2.5 text-right align-top ${
                    showsPositive(f.alpha_annual) ? "text-accent-ink" : ""
                  }`}
                >
                  {spct(f.alpha_annual)}
                </td>
                <td className="num px-2 py-2.5 text-right align-top">{tstat(f.alpha_t)}</td>
                <td className="num px-2 py-2.5 text-right align-top">{dec(f.r2)}</td>
                <td className="num py-2.5 pl-2 text-right align-top">{share(f.factor_share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
