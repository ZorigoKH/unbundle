"use client";

import { useRouter } from "next/navigation";
import { type KeyboardEvent, type MouseEvent, type PointerEvent, useMemo, useState } from "react";

import { er, spct, tickPct, tstat } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { textWidth, useWidth } from "./useWidth";

export type ScatterPoint = {
  ticker: string;
  name: string;
  /** "active fund", "index fund", ...: shown in the readout. */
  kind: string;
  active: boolean;
  er: number;
  alpha: number;
  lo: number;
  hi: number;
  t: number;
};

const HIT = 28; // px: how close the pointer must be to pick a point

/**
 * Expense ratio (x) against Carhart alpha after fees (y), one dot per fund with its 95%
 * interval. Actively managed portfolios are filled dots in the accent, index/factor/sector
 * funds hollow rings in the context gray, so the groups differ in shape as well as colour.
 * Hover, tap or arrow keys pick a fund; click, a second tap or Enter opens it.
 */
export function AlphaScatter({ points, label }: { points: ScatterPoint[]; label: string }) {
  const router = useRouter();
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const [active, setActive] = useState<number | null>(null);

  // Keyboard order: left to right, then bottom to top.
  const order = useMemo(
    () =>
      points
        .map((p, i) => ({ p, i }))
        .sort((a, b) => a.p.er - b.p.er || a.p.alpha - b.p.alpha)
        .map((o) => o.i),
    [points],
  );

  const height = width < 520 ? 320 : 400;
  const top = 12;
  const bottom = height - 30;
  const left = 48;
  const right = width - 14;
  // Scales fit the data; ticks are the round values inside it.
  const xMax = Math.max(...points.map((p) => p.er)) * 1.04;
  const yLo = Math.min(0, ...points.map((p) => p.lo));
  const yHi = Math.max(0, ...points.map((p) => p.hi));
  const yPad = (yHi - yLo) * 0.03;
  const x = linear([0, xMax], [left + 6, right]);
  const y = linear([yLo - yPad, yHi + yPad], [bottom, top]);
  const xTicks = niceTicks(0, xMax, Math.max(4, Math.floor((right - left) / 80))).ticks.filter(
    (t) => t <= xMax,
  );
  const yTicks = niceTicks(yLo, yHi, height < 360 ? 5 : 7).ticks.filter(
    (t) => t >= yLo - yPad && t <= yHi + yPad,
  );

  function nearest(e: PointerEvent<SVGSVGElement> | MouseEvent<SVGSVGElement>): number | null {
    const rect = e.currentTarget.getBoundingClientRect();
    const scale = width / rect.width;
    const px = (e.clientX - rect.left) * scale;
    const py = (e.clientY - rect.top) * scale;
    let best: number | null = null;
    let bestD = HIT * HIT;
    for (let i = 0; i < points.length; i++) {
      const p = points[i]!;
      const d = (x(p.er) - px) ** 2 + (y(p.alpha) - py) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    return best;
  }

  const open = (i: number) => router.push(`/fund/${points[i]!.ticker}`);

  function onClick(e: MouseEvent<SVGSVGElement>) {
    const i = nearest(e);
    if (i === null) return;
    // A mouse has already picked the point by hovering; a first tap only picks it.
    if (i === active) open(i);
    else setActive(i);
  }

  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    const pos = active === null ? -1 : order.indexOf(active);
    let next: number | null | undefined;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = order[(pos + 1) % order.length];
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp")
      next = order[(pos - 1 + order.length) % order.length];
    else if (e.key === "Home") next = order[0];
    else if (e.key === "End") next = order.at(-1);
    else if (e.key === "Escape") next = null;
    else if (e.key === "Enter" && active !== null) {
      e.preventDefault();
      open(active);
      return;
    }
    if (next === undefined) return;
    e.preventDefault();
    setActive(next);
  }

  const sel = active === null ? null : points[active]!;
  const selLabel = sel ? `${sel.ticker} ${spct(sel.alpha)}` : "";
  const selW = textWidth(selLabel, 12);
  const selX = sel ? x(sel.er) : 0;
  const selLeft = sel ? selX + 10 + selW > right : false;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="flex items-center gap-2">
          <svg width="12" height="12" aria-hidden="true">
            <circle cx="6" cy="6" r="4.5" fill="var(--accent)" />
          </svg>
          actively managed
        </span>
        <span className="flex items-center gap-2">
          <svg width="12" height="12" aria-hidden="true">
            <circle
              cx="6"
              cy="6"
              r="3.75"
              fill="var(--bg)"
              stroke="var(--context)"
              strokeWidth="1.75"
            />
          </svg>
          index, factor and sector funds
        </span>
        <span className="flex items-center gap-2 text-muted">
          <svg width="10" height="14" aria-hidden="true">
            <line x1="5" x2="5" y1="1" y2="13" stroke="var(--muted)" strokeWidth="1.5" />
          </svg>
          95% interval
        </span>
      </div>
      <p className="mb-1 text-xs text-muted">alpha after fees, % a year</p>
      <div ref={ref}>
        <svg
          className="chart cursor-pointer"
          role="img"
          aria-label={label}
          aria-describedby="scatter-hint"
          tabIndex={0}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          onPointerMove={(e) => {
            if (e.pointerType === "mouse") setActive(nearest(e));
          }}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") setActive(null);
          }}
          onClick={onClick}
          onKeyDown={onKey}
          onBlur={() => setActive(null)}
        >
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line
                x1={left}
                x2={right}
                y1={y(t)}
                y2={y(t)}
                stroke={t === 0 ? "var(--base)" : "var(--grid)"}
                strokeWidth={t === 0 ? 1.5 : 1}
                shapeRendering="crispEdges"
              />
              <text
                x={left - 8}
                y={y(t) + 4}
                textAnchor="end"
                fontSize={11}
                className="text-muted num"
              >
                {tickPct(t)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <g key={`x${t}`}>
              <line
                x1={x(t)}
                x2={x(t)}
                y1={bottom}
                y2={bottom + 4}
                stroke="var(--base)"
                shapeRendering="crispEdges"
              />
              <text
                x={x(t)}
                y={bottom + 18}
                textAnchor="middle"
                fontSize={11}
                className="text-muted num"
              >
                {tickPct(t)}
              </text>
            </g>
          ))}
          {points.map((p, i) => (
            <line
              key={`ci${p.ticker}`}
              x1={x(p.er)}
              x2={x(p.er)}
              y1={y(p.lo)}
              y2={y(p.hi)}
              stroke={p.active ? "var(--accent)" : "var(--context)"}
              strokeWidth={i === active ? 2 : 1}
              opacity={active === null || i === active ? 0.55 : 0.2}
            />
          ))}
          {points.map((p, i) =>
            p.active ? (
              <circle
                key={p.ticker}
                cx={x(p.er)}
                cy={y(p.alpha)}
                r={4.5}
                fill="var(--accent)"
                stroke="var(--bg)"
                strokeWidth={2}
                opacity={active === null || i === active ? 1 : 0.45}
              />
            ) : (
              <circle
                key={p.ticker}
                cx={x(p.er)}
                cy={y(p.alpha)}
                r={3.75}
                fill="var(--bg)"
                stroke="var(--context)"
                strokeWidth={1.75}
                opacity={active === null || i === active ? 1 : 0.45}
              />
            ),
          )}
          {sel && (
            <g pointerEvents="none">
              <circle
                cx={selX}
                cy={y(sel.alpha)}
                r={8}
                fill="none"
                stroke="var(--fg)"
                strokeWidth={1.5}
              />
              <text
                x={selLeft ? selX - 12 : selX + 12}
                y={y(sel.alpha) - 10}
                textAnchor={selLeft ? "end" : "start"}
                fontSize={12}
                className="text-fg num"
                paintOrder="stroke"
                stroke="var(--bg)"
                strokeWidth={4}
                strokeLinejoin="round"
              >
                {selLabel}
              </text>
            </g>
          )}
        </svg>
      </div>
      <p className="mt-1 text-right text-xs text-muted">expense ratio, % a year</p>
      <p className="mt-3 min-h-[3rem] text-sm" aria-live="polite">
        {sel ? (
          <>
            <span className="font-medium">{sel.ticker}</span>{" "}
            <span className="text-muted">
              {sel.name} · {sel.kind}
            </span>
            <br />
            <span className="tabular-nums">
              expense ratio {er(sel.er)} · alpha after fees {spct(sel.alpha)} a year (95%{" "}
              {spct(sel.lo)} to {spct(sel.hi)}) · t = {tstat(sel.t)}
            </span>
          </>
        ) : (
          <span className="text-muted">
            Hover or tap a dot to see the fund; click or tap again to open it.
          </span>
        )}
      </p>
      <p id="scatter-hint" className="sr-only">
        Focus the chart and use the arrow keys to step through funds by expense ratio; press
        Enter to open the selected fund. Each fund&rsquo;s expense ratio, alpha and t-statistic
        are also in the table above, and its 95% interval is on its own page.
      </p>
    </div>
  );
}
