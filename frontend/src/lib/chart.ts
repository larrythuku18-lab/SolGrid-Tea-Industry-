interface Point {
  x: number;
  y: number;
}

/** Quadratic-bezier-through-segment-midpoints — a cheap, dependency-free
 * way to round off a polyline without pulling in a charting/spline
 * library. Every original point still lies on the curve; only the
 * approach between them is smoothed. */
export function smoothPath(points: Point[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

  let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i];
    const p1 = points[i + 1];
    const midX = (p0.x + p1.x) / 2;
    const midY = (p0.y + p1.y) / 2;
    d += ` Q ${p0.x.toFixed(1)} ${p0.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`;
  }
  const last = points[points.length - 1];
  d += ` L ${last.x.toFixed(1)} ${last.y.toFixed(1)}`;
  return d;
}

/** A bar/column mark: rounded at the data end, square at the baseline —
 * `<rect rx>` rounds all four corners, which reads as a heavier, more
 * generic shape than a considered chart mark. `radius` is clamped to the
 * bar's own size so a very short bar never produces a malformed path. */
export function roundedTopBarPath(x: number, y: number, width: number, height: number, radius: number): string {
  const r = Math.max(0, Math.min(radius, height, width / 2));
  if (r === 0) {
    return `M ${x.toFixed(1)} ${(y + height).toFixed(1)} L ${x.toFixed(1)} ${y.toFixed(1)} L ${(x + width).toFixed(1)} ${y.toFixed(1)} L ${(x + width).toFixed(1)} ${(y + height).toFixed(1)} Z`;
  }
  return [
    `M ${x.toFixed(1)} ${(y + height).toFixed(1)}`,
    `L ${x.toFixed(1)} ${(y + r).toFixed(1)}`,
    `Q ${x.toFixed(1)} ${y.toFixed(1)} ${(x + r).toFixed(1)} ${y.toFixed(1)}`,
    `L ${(x + width - r).toFixed(1)} ${y.toFixed(1)}`,
    `Q ${(x + width).toFixed(1)} ${y.toFixed(1)} ${(x + width).toFixed(1)} ${(y + r).toFixed(1)}`,
    `L ${(x + width).toFixed(1)} ${(y + height).toFixed(1)}`,
    "Z",
  ].join(" ");
}
