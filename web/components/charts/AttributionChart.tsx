"use client";

import { dec, spct, tickPct } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { hbarPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

export type AttributionRow = {
  key: string;
  label: string;
  /** Factor loading; absent for the alpha row. */
  beta?: number;
  /** Annual contribution to the excess return, decimal. */
  value: number;
};

const FONT = 12;
const ROW = 42;
const BAR = 18;
const LABEL_W = 104;
const AXIS_H = 26;

/**
 * One horizontal bar per factor contribution plus alpha, from a shared zero baseline. Alpha
 * is in the accent, factor exposure in the context gray; every bar carries its value.
 */
export function AttributionChart({
  rows,
  excess,
  label,
}: {
  rows: AttributionRow[];
  excess: number;
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const values = rows.map((r) => r.value);
  const labels = values.map((v) => spct(v));
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const labelRoom = Math.max(...labels.map((s) => textWidth(s, FONT))) + 10;
  const left = LABEL_W + (lo < 0 ? labelRoom : 8);
  const right = width - (hi > 0 ? labelRoom : 8);
  const { ticks } = niceTicks(lo, hi, Math.max(2, Math.floor((right - left) / 70)));
  const x = linear([lo, hi], [left, right]);
  const inside = ticks.filter((t) => t >= lo - 1e-12 && t <= hi + 1e-12);
  const height = rows.length * ROW + AXIS_H + 4;
  const plotBottom = rows.length * ROW;

  return (
    <div ref={ref}>
      <svg
        className="chart"
        role="img"
        aria-label={label}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
      >
        {inside.map((t) => (
          <g key={t}>
            <line
              x1={x(t)}
              x2={x(t)}
              y1={0}
              y2={plotBottom}
              stroke={t === 0 ? "var(--base)" : "var(--grid)"}
              strokeWidth={1}
              shapeRendering="crispEdges"
            />
            <text
              x={x(t)}
              y={plotBottom + 18}
              textAnchor="middle"
              fontSize={11}
              className="text-muted"
            >
              {tickPct(t)}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = i * ROW + (ROW - BAR) / 2;
          const x0 = x(0);
          const x1 = x(r.value);
          const alpha = r.key === "alpha";
          const tip = r.value >= 0 ? x1 + 6 : x1 - 6;
          return (
            <g key={r.key}>
              <text x={0} y={i * ROW + ROW / 2 - 2} fontSize={13} className="text-fg">
                {r.label}
              </text>
              <text x={0} y={i * ROW + ROW / 2 + 13} fontSize={11} className="text-muted">
                {r.beta === undefined ? "after fees" : `β ${dec(r.beta)}`}
              </text>
              <path
                d={hbarPath(x0, x1, y, BAR)}
                fill={alpha ? "var(--accent)" : "var(--context)"}
              />
              <text
                x={tip}
                y={y + BAR / 2 + 4}
                fontSize={FONT}
                textAnchor={r.value >= 0 ? "start" : "end"}
                className="text-fg num"
              >
                {labels[i]}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-3 border-t border-line pt-3 text-sm">
        <span className="text-muted">sum = excess return over T-bills </span>
        <span className="num">{spct(excess)}</span>
        <span className="text-muted"> a year</span>
      </p>
    </div>
  );
}
