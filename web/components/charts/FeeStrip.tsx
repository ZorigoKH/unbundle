"use client";

import { er, spct, tickPct } from "@/lib/format";
import { linear, niceTicks } from "@/lib/scale";

import { hbarPath } from "./marks";
import { textWidth, useWidth } from "./useWidth";

const FONT = 12;
const ROW = 36;
const LABEL_W = 104;
const AXIS_H = 26;

/**
 * Three rows on one percent-a-year scale: the value the manager added before fees (gross
 * alpha), the fee that came out of it, and what was left for investors (net alpha) with its
 * 95% interval.
 */
export function FeeStrip({
  gross,
  fee,
  net,
  ci,
  label,
}: {
  gross: number;
  fee: number;
  net: number;
  ci: [number, number];
  label: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const values = [spct(gross), fee > 0 ? `−${er(fee)}` : "none", spct(net)];
  const valueW = Math.max(...values.map((s) => textWidth(s, FONT))) + 16;
  const left = LABEL_W;
  const right = width - valueW;
  const lo = Math.min(0, ci[0], gross, net);
  const hi = Math.max(0, ci[1], gross, net);
  const pad = (hi - lo) * 0.04;
  const { ticks } = niceTicks(lo, hi, Math.max(3, Math.floor((right - left) / 70)));
  const x = linear([lo - pad, hi + pad], [left, right]);
  const inside = ticks.filter((t) => t >= lo - pad && t <= hi + pad);
  const plotBottom = 3 * ROW;
  const height = plotBottom + AXIS_H;
  const cy = (i: number) => i * ROW + ROW / 2;
  const rowLabels = ["before fees", "fee", "after fees"];

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
              className="text-muted num"
            >
              {tickPct(t)}
            </text>
          </g>
        ))}
        {rowLabels.map((l, i) => (
          <g key={l}>
            <text x={0} y={cy(i) + 4} fontSize={13} className="text-fg">
              {l}
            </text>
            <text
              x={width}
              y={cy(i) + 4}
              textAnchor="end"
              fontSize={FONT}
              className="text-fg num"
            >
              {values[i]}
            </text>
          </g>
        ))}

        {/* before fees: an open accent ring at the gross alpha */}
        <circle
          cx={x(gross)}
          cy={cy(0)}
          r={5}
          fill="var(--bg)"
          stroke="var(--accent)"
          strokeWidth={2}
        />

        {/* the fee: a gray bar from gross alpha down to net alpha */}
        {fee > 0 && <path d={hbarPath(x(gross), x(net), cy(1) - 7, 14)} fill="var(--context)" />}
        <line
          x1={x(gross)}
          x2={x(gross)}
          y1={cy(0) + 7}
          y2={cy(2) - 7}
          stroke="var(--grid)"
          strokeWidth={1}
          strokeDasharray="2 3"
        />

        {/* after fees: the net alpha with its 95% interval */}
        <line
          x1={x(ci[0])}
          x2={x(ci[1])}
          y1={cy(2)}
          y2={cy(2)}
          stroke="var(--accent)"
          strokeWidth={1.5}
        />
        {ci.map((v, i) => (
          <line
            key={i}
            x1={x(v)}
            x2={x(v)}
            y1={cy(2) - 5}
            y2={cy(2) + 5}
            stroke="var(--accent)"
            strokeWidth={1.5}
          />
        ))}
        <circle
          cx={x(net)}
          cy={cy(2)}
          r={5}
          fill="var(--accent)"
          stroke="var(--bg)"
          strokeWidth={2}
        />
      </svg>
    </div>
  );
}
