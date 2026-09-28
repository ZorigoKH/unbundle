"use client";

import { type KeyboardEvent, type PointerEvent, useCallback, useRef, useState } from "react";

import { dollars, month, monthIndex } from "@/lib/format";
import { linePath, linear, log, logTicks, spread, yearTicks } from "@/lib/scale";
import type { Growth } from "@/lib/types";

import { useTapOutside } from "./useTapOutside";
import { textWidth, useWidth } from "./useWidth";

const FONT = 12;

type Series = {
  key: "fund" | "replica" | "tbills";
  name: string;
  color: string;
  dash?: string;
  width: number;
};

/**
 * Growth of $1 over the headline window on a log axis: the fund in the accent, T-bills plus
 * the fund's own factor exposure in the context gray, T-bills alone dashed. Hover, tap or
 * arrow keys move a readout; at rest the readout shows the final values. A tapped month
 * stays until the reader taps outside the chart.
 */
export function GrowthChart({
  growth,
  ticker,
  label,
}: {
  growth: Growth;
  ticker: string;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const [active, setActive] = useState<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const clear = useCallback(() => setActive(null), []);
  useTapOutside(root, active !== null, clear);

  const series: Series[] = [
    { key: "tbills", name: "T-bills", color: "var(--context)", dash: "5 4", width: 1.5 },
    {
      key: "replica",
      name: "T-bills + the same factor exposure",
      color: "var(--context)",
      width: 2,
    },
    { key: "fund", name: ticker, color: "var(--accent)", width: 2 },
  ];

  const n = growth.months.length;
  const last = n - 1;
  const all = [...growth.fund, ...growth.replica, ...growth.tbills];
  const lo = Math.min(...all) * 0.97;
  const hi = Math.max(...all) * 1.03;
  const ends = series.map((s) => dollars(growth[s.key][last]!));
  const endRoom = Math.max(...ends.map((s) => textWidth(s, FONT))) + 18;

  const height = width < 520 ? 240 : 320;
  const top = 10;
  const bottom = height - 26;
  const left = 46;
  const right = width - endRoom;
  const m0 = monthIndex(growth.months[0]!);
  const m1 = monthIndex(growth.months[last]!);
  const x = linear([m0, m1], [left, right]);
  const y = log([lo, hi], [bottom, top]);
  const xs = growth.months.map((m) => x(monthIndex(m)));
  const yTicks = logTicks(lo, hi, height < 300 ? 5 : 6);
  const xTicks = yearTicks(m0, m1, Math.floor((right - left) / 64));
  const endYs = spread(
    series.map((s) => y(growth[s.key][last]!)),
    FONT + 3,
    top + 4,
    bottom,
  );

  const shown = active ?? last;

  function indexAt(e: PointerEvent<SVGSVGElement>): number {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const t = (px - left) / (right - left);
    return Math.max(0, Math.min(last, Math.round(t * last)));
  }

  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    const cur = active ?? last;
    const step = e.shiftKey ? 12 : 1;
    const next =
      e.key === "ArrowLeft"
        ? cur - step
        : e.key === "ArrowRight"
          ? cur + step
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? last
              : e.key === "Escape"
                ? null
                : undefined;
    if (next === undefined) return;
    e.preventDefault();
    setActive(next === null ? null : Math.max(0, Math.min(last, next)));
  }

  return (
    <div ref={root}>
      <div className="mb-3 flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:gap-x-6">
        <span className="text-muted num">{month(growth.months[shown]!)}</span>
        {[...series].reverse().map((s) => (
          <span key={s.key} className="flex items-start gap-2">
            <svg width="22" height="8" aria-hidden="true" className="mt-[0.5lh] shrink-0 -translate-y-1/2">
              <line
                x1="1"
                x2="21"
                y1="4"
                y2="4"
                stroke={s.color}
                strokeWidth={s.width}
                strokeDasharray={s.dash}
                strokeLinecap="round"
              />
            </svg>
            <span>
              <span className={s.key === "fund" ? "" : "text-muted"}>{s.name}</span>{" "}
              <span className="num">{dollars(growth[s.key][shown]!)}</span>
            </span>
          </span>
        ))}
      </div>
      <div ref={ref}>
        <svg
          className="chart outline-none focus-visible:outline-2"
          role="img"
          aria-label={label}
          aria-describedby="growth-hint"
          tabIndex={0}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          onPointerMove={(e) => setActive(indexAt(e))}
          onPointerDown={(e) => setActive(indexAt(e))}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") clear();
          }}
          onKeyDown={onKey}
          onBlur={clear}
        >
          {yTicks.map((t) => (
            <g key={t}>
              <line
                x1={left}
                x2={right}
                y1={y(t)}
                y2={y(t)}
                stroke={t === 1 ? "var(--base)" : "var(--grid)"}
                strokeWidth={1}
                shapeRendering="crispEdges"
              />
              <text
                x={left - 8}
                y={y(t) + 4}
                textAnchor="end"
                fontSize={11}
                className="text-muted num"
              >
                {t < 1 ? `$${t.toFixed(2)}` : `$${t}`}
              </text>
            </g>
          ))}
          {xTicks.map((m) => (
            <g key={m}>
              <line
                x1={x(m)}
                x2={x(m)}
                y1={bottom}
                y2={bottom + 4}
                stroke="var(--base)"
                shapeRendering="crispEdges"
              />
              <text
                x={x(m)}
                y={bottom + 18}
                textAnchor="middle"
                fontSize={11}
                className="text-muted num"
              >
                {m / 12}
              </text>
            </g>
          ))}
          {series.map((s) => (
            <path
              key={s.key}
              d={linePath(
                xs,
                growth[s.key].map((v) => y(v)),
              )}
              fill="none"
              stroke={s.color}
              strokeWidth={s.width}
              strokeDasharray={s.dash}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {series.map((s, i) => {
            const v = growth[s.key][last]!;
            return (
              <g key={s.key}>
                <circle
                  cx={right}
                  cy={y(v)}
                  r={4}
                  fill={s.color}
                  stroke="var(--bg)"
                  strokeWidth={2}
                />
                <text
                  x={right + 10}
                  y={endYs[i]! + 4}
                  fontSize={FONT}
                  className={`num ${s.key === "fund" ? "text-fg" : "text-muted"}`}
                >
                  {ends[i]}
                </text>
              </g>
            );
          })}
          {active !== null && (
            <g pointerEvents="none">
              <line
                x1={xs[active]}
                x2={xs[active]}
                y1={top}
                y2={bottom}
                stroke="var(--muted)"
                strokeWidth={1}
                shapeRendering="crispEdges"
              />
              {series.map((s) => (
                <circle
                  key={s.key}
                  cx={xs[active]}
                  cy={y(growth[s.key][active]!)}
                  r={4}
                  fill={s.color}
                  stroke="var(--bg)"
                  strokeWidth={2}
                />
              ))}
            </g>
          )}
        </svg>
      </div>
      <p id="growth-hint" className="sr-only">
        Values for each month appear above the chart. Use the left and right arrow keys to move
        one month, with shift to move a year.
      </p>
    </div>
  );
}
