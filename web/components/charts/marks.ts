// Shared SVG mark geometry.

/**
 * A horizontal bar from `x0` (the baseline) to `x1` with a rounded data end and a square
 * baseline end, per the chart mark spec.
 */
export function hbarPath(x0: number, x1: number, y: number, h: number, r = 4): string {
  const w = Math.abs(x1 - x0);
  if (w < 0.5) return "";
  const rr = Math.min(r, w, h / 2);
  const dir = x1 >= x0 ? 1 : -1;
  const xe = x1 - dir * rr;
  return [
    `M${x0},${y}`,
    `H${xe}`,
    `Q${x1},${y} ${x1},${y + rr}`,
    `V${y + h - rr}`,
    `Q${x1},${y + h} ${xe},${y + h}`,
    `H${x0}`,
    "Z",
  ].join(" ");
}
