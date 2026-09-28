"use client";

import { type PointerEvent, useCallback, useRef, useState } from "react";

import { dec, month, monthIndex, spct, tickNum, tickPct } from "@/lib/format";
import { linePath, linear, niceTicks, yearTicks } from "@/lib/scale";

import { useTapOutside } from "./useTapOutside";
import { useWidth } from "./useWidth";

export type RollingSeries = {
  key: string;
  title: string;
  values: number[];
  /** Reference line: 0 for alpha and tilts, 1 for the market beta; null for none. */
  reference: number | null;
  /** "pct" formats values as percent a year; "num" as plain decimals. */
  format: "pct" | "num";
  /** Line colour: the accent for alpha, the context gray for factor exposure and R². */
  color: string;
};

type PanelProps = {
  series: RollingSeries & { shown: string };
  months: string[];
  window: { start: string; end: string };
  active: number | null;
  setActive: (i: number | null) => void;
};

const HEIGHT = 120;

function Panel({ series, months, window, active, setActive }: PanelProps) {
  const [ref, width] = useWidth<HTMLDivElement>(300);
  const n = months.length;
  const last = n - 1;
  const left = 44;
  const right = width - 8;
  const top = 8;
  const bottom = HEIGHT - 22;

  const m0 = monthIndex(months[0]!);
  const m1 = monthIndex(months[last]!);
  const x = linear([m0, Math.max(m1, m0 + 1)], [left, right]);
  const vals = series.values;
  const extent = [...vals, ...(series.reference === null ? [] : [series.reference])];
  const vlo = Math.min(...extent);
  const vhi = Math.max(...extent);
  const pad = (vhi - vlo) * 0.08 || 0.05;
  const { ticks, domain } = niceTicks(vlo - pad, vhi + pad, 3);
  const y = linear(domain, [bottom, top]);
  const xs = months.map((m) => x(monthIndex(m)));
  const xTicks = yearTicks(m0, m1, Math.max(2, Math.floor((right - left) / 56)));
  const fmt = series.format === "pct" ? tickPct : tickNum;

  // Shade the headline window so the rolling view lines up with the numbers above it.
  const w0 = Math.max(m0, monthIndex(window.start));
  const w1 = Math.min(m1, monthIndex(window.end));

  function indexAt(e: PointerEvent<SVGSVGElement>): number {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const t = (px - left) / (right - left);
    return Math.max(0, Math.min(last, Math.round(t * last)));
  }

  const i = active ?? last;
  const show = (v: number) => (series.format === "pct" ? spct(v) : dec(v, 2));
  const summary =
    `${series.title}, rolling 36 months: ${show(vals[0]!)} in ${month(months[0]!)}, ` +
    `${show(vals[last]!)} in ${month(months[last]!)}; ` +
    `lowest ${show(Math.min(...vals))}, highest ${show(Math.max(...vals))}.`;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>{series.title}</span>
        <span className="num text-muted">{series.shown}</span>
      </div>
      <div ref={ref}>
        <svg
          className="chart"
          role="img"
          aria-label={summary}
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          onPointerMove={(e) => setActive(indexAt(e))}
          onPointerDown={(e) => setActive(indexAt(e))}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") setActive(null);
          }}
        >
          {w1 > w0 && (
            <rect
              x={x(w0)}
              y={top}
              width={Math.round((x(w1) - x(w0)) * 100) / 100}
              height={bottom - top}
              fill="var(--grid)"
              opacity={0.45}
            />
          )}
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={left}
                x2={right}
                y1={y(t)}
                y2={y(t)}
                stroke="var(--grid)"
                strokeWidth={1}
                shapeRendering="crispEdges"
              />
              <text
                x={left - 6}
                y={y(t) + 4}
                textAnchor="end"
                fontSize={10}
                className="text-muted num"
              >
                {fmt(t)}
              </text>
            </g>
          ))}
          {series.reference !== null && (
            <line
              x1={left}
              x2={right}
              y1={y(series.reference)}
              y2={y(series.reference)}
              stroke="var(--base)"
              strokeWidth={1.5}
              shapeRendering="crispEdges"
            />
          )}
          {xTicks.map((m) => (
            <text
              key={m}
              x={x(m)}
              y={bottom + 15}
              textAnchor="middle"
              fontSize={10}
              className="text-muted num"
            >
              {m / 12}
            </text>
          ))}
          <path
            d={linePath(
              xs,
              vals.map((v) => y(v)),
            )}
            fill="none"
            stroke={series.color}
            strokeWidth={1.5}
            strokeLinejoin="round"
          />
          {active !== null && (
            <line
              x1={xs[i]}
              x2={xs[i]}
              y1={top}
              y2={bottom}
              stroke="var(--muted)"
              strokeWidth={1}
              shapeRendering="crispEdges"
            />
          )}
          <circle
            cx={xs[i]}
            cy={y(vals[i]!)}
            r={3.5}
            fill={series.color}
            stroke="var(--bg)"
            strokeWidth={2}
          />
        </svg>
      </div>
    </div>
  );
}

/**
 * Small multiples of the rolling 36-month Carhart fit: alpha and each factor loading, one
 * panel each, sharing a hover month. The shaded span is the headline window. A tapped month
 * stays until the reader taps outside the panels.
 */
export function RollingPanels({
  months,
  series,
  window,
  label,
}: {
  months: string[];
  series: RollingSeries[];
  window: { start: string; end: string };
  label: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const root = useRef<HTMLElement>(null);
  const clear = useCallback(() => setActive(null), []);
  useTapOutside(root, active !== null, clear);
  const last = months.length - 1;
  const i = active ?? last;
  const show = (s: RollingSeries) => {
    const v = s.values[i]!;
    return s.format === "pct" ? `${spct(v)} a year` : dec(v, 2);
  };

  return (
    <figure ref={root} role="group" aria-label={label}>
      <p className="mb-4 text-sm text-muted">
        36 months ending <span className="num text-fg">{month(months[i]!)}</span>
        {active === null ? " (latest)" : ""}
      </p>
      <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
        {series.map((s) => (
          <Panel
            key={s.key}
            series={{ ...s, shown: show(s) }}
            months={months}
            window={window}
            active={active}
            setActive={setActive}
          />
        ))}
      </div>
    </figure>
  );
}
