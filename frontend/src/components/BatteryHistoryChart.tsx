import { smoothPath } from "../lib/chart";
import { formatMonthLabel, parseIsoInstant } from "../lib/dates";
import type { SolarHealthPoint } from "../types/api";

interface BatteryHistoryChartProps {
  points: SolarHealthPoint[];
  /** Time domain for the x axis. Readings ingested live land at irregular
   * intervals — seconds apart from a device feed, days apart from the seeded
   * daily history — so plotting by array index would give a reading taken
   * seconds after the last one the same room on the chart as a gap of a
   * week. Falls back to the data's own span when omitted. */
  domainStart?: string;
  domainEnd?: string;
}

const WIDTH = 720;
const HEIGHT = 220;
const PAD_LEFT = 40;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 26;
const TICK_COUNT = 6;

const ms = (iso: string) => parseIsoInstant(iso).getTime();

/** Daily-resolution SoC/SoH history — dozens to hundreds of points, not the
 * handful the monthly ledger-backed charts have, so this is deliberately a
 * plain two-line chart rather than trying to reuse GenerationChart's
 * bars-plus-line layout (which assumes few, evenly-labelable periods). */
export function BatteryHistoryChart({ points, domainStart, domainEnd }: BatteryHistoryChartProps) {
  if (points.length === 0) {
    return <div className="empty-state">No battery/panel telemetry for this period.</div>;
  }

  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const startMs = domainStart ? ms(domainStart) : ms(points[0].ts);
  // The domain has to stretch to cover the newest point even when it
  // postdates the period the page asked for: a reading that just arrived
  // lands *after* the window's end, and clamping the axis to the window
  // would pin every live reading to the same clipped right edge.
  const endMs = Math.max(domainEnd ? ms(domainEnd) : startMs, ms(points[points.length - 1].ts));
  const spanMs = Math.max(endMs - startMs, 1);

  const yFor = (v: number) => PAD_TOP + plotHeight - (v / 100) * plotHeight;
  const xFor = (iso: string) => {
    const ratio = (ms(iso) - startMs) / spanMs;
    // Clamped, so a point outside the domain is drawn on the edge of the plot
    // rather than in the axis label gutter or outside the SVG entirely.
    return PAD_LEFT + Math.min(1, Math.max(0, ratio)) * plotWidth;
  };

  const socPoints = points
    .map((p) => (p.battery_soc_pct !== null ? { x: xFor(p.ts), y: yFor(p.battery_soc_pct) } : null))
    .filter((p): p is { x: number; y: number } => p !== null);
  const sohPoints = points
    .map((p) => (p.battery_soh_pct !== null ? { x: xFor(p.ts), y: yFor(p.battery_soh_pct) } : null))
    .filter((p): p is { x: number; y: number } => p !== null);

  const baselineY = yFor(0);
  const socArea =
    socPoints.length > 1
      ? `${smoothPath(socPoints)} L ${socPoints[socPoints.length - 1].x.toFixed(1)} ${baselineY.toFixed(1)} L ${socPoints[0].x.toFixed(1)} ${baselineY.toFixed(1)} Z`
      : "";

  // Ticks placed evenly in *time*, not by index, and collapsed when two land
  // inside the same month — an 8-month window gets month names, and a
  // short one doesn't repeat the same label twice.
  const ticks: { x: number; label: string; anchor: "start" | "middle" | "end" }[] = [];
  for (let i = 0; i < TICK_COUNT; i++) {
    const at = startMs + (spanMs * i) / (TICK_COUNT - 1);
    const label = formatMonthLabel(new Date(at).toISOString());
    if (ticks.length > 0 && ticks[ticks.length - 1].label === label) continue;
    ticks.push({
      x: PAD_LEFT + (plotWidth * i) / (TICK_COUNT - 1),
      label,
      anchor: i === 0 ? "start" : i === TICK_COUNT - 1 ? "end" : "middle",
    });
  }

  const newestSoc = socPoints.length > 0 ? socPoints[socPoints.length - 1] : null;
  const gridFractions = [0, 25, 50, 75, 100];

  return (
    <div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart-svg"
        role="img"
        aria-label="Battery state of charge and state of health over time"
      >
        <defs>
          <linearGradient id="soc-area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--volt)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--volt)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {gridFractions.map((v) => (
          <g key={v}>
            <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={yFor(v)} y2={yFor(v)} className="chart-gridline" />
            <text x={PAD_LEFT - 8} y={yFor(v)} textAnchor="end" dominantBaseline="middle" className="chart-axis-label">
              {v}%
            </text>
          </g>
        ))}

        {socArea !== "" && <path d={socArea} className="chart-area" fill="url(#soc-area-fill)" />}

        <path d={smoothPath(sohPoints)} className="chart-line chart-line-soh" fill="none" />
        <path d={smoothPath(socPoints)} className="chart-line chart-line-soc" fill="none" />

        {ticks.map((t) => (
          <text key={`${t.label}-${t.x}`} x={t.x} y={HEIGHT - 6} textAnchor={t.anchor} className="chart-axis-label">
            {t.label}
          </text>
        ))}

        {newestSoc !== null && (
          <g key={`newest-${points.length}`}>
            {/* Vertical flash at the newest reading: the chart's own "write
                head", so an arrival is visible without moving the whole
                curve. Keyed on the point count so it replays on each one. */}
            <line
              className="chart-sweep"
              x1={newestSoc.x}
              x2={newestSoc.x}
              y1={PAD_TOP}
              y2={PAD_TOP + plotHeight}
            />
            <circle cx={newestSoc.x} cy={newestSoc.y} r={7} className="chart-halo" />
            <circle cx={newestSoc.x} cy={newestSoc.y} r={3.4} className="chart-dot chart-dot-live" />
          </g>
        )}
      </svg>

      <div className="mix-legend">
        <span className="leg">
          <span className="swatch-line soc" />
          Battery state of charge
        </span>
        <span className="leg">
          <span className="swatch-line soh" />
          Battery state of health
        </span>
      </div>
    </div>
  );
}
