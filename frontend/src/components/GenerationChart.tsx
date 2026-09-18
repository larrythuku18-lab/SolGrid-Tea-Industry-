import { smoothPath } from "../lib/chart";
import { formatMonthLabel, parseIsoInstant } from "../lib/dates";
import type { GenerationVsConsumptionPoint } from "../types/api";

interface GenerationChartProps {
  points: GenerationVsConsumptionPoint[];
  /** Time domain for the x axis, so a new month appearing doesn't rescale
   * every bar already on the chart. Falls back to the data's own span. */
  domainStart?: string;
  domainEnd?: string;
}

const WIDTH = 720;
const HEIGHT = 260;
const PAD_LEFT = 54;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;
const MAX_BAR_WIDTH = 30;

const ms = (iso: string) => parseIsoInstant(iso).getTime();

function formatCompact(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(value));
}

/** Real chart, not a decorative one: bars for solar generation, a line for
 * total electrical consumption (grid + diesel-equivalent + solar), plotted
 * to the same axis so the overlap — self-consumption — is visible directly
 * rather than left for the reader to compute from two separate numbers. */
export function GenerationChart({ points, domainStart, domainEnd }: GenerationChartProps) {
  if (points.length === 0) {
    return <div className="empty-state">No solar generation data for this period.</div>;
  }

  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const maxVal = Math.max(
    ...points.map((p) => Math.max(p.generation_kwh, p.consumption_kwh, p.expected_generation_kwh ?? 0)),
    1,
  );

  const midpointMs = (p: GenerationVsConsumptionPoint) => (ms(p.period_start) + ms(p.period_end)) / 2;
  const startMs = domainStart ? ms(domainStart) : ms(points[0].period_start);
  const endMs = Math.max(
    domainEnd ? ms(domainEnd) : startMs,
    ...points.map((p) => ms(p.period_end)),
  );
  const spanMs = Math.max(endMs - startMs, 1);

  const xForMs = (value: number) => {
    const ratio = (value - startMs) / spanMs;
    return PAD_LEFT + Math.min(1, Math.max(0, ratio)) * plotWidth;
  };
  const yFor = (v: number) => PAD_TOP + plotHeight - (v / maxVal) * plotHeight;
  // Bars are as wide as the period they cover would suggest, capped so a
  // single-month window doesn't produce one enormous bar. This is also what
  // keeps a freshly-appended month from resizing the older ones.
  const widthFor = (p: GenerationVsConsumptionPoint) =>
    Math.max(3, Math.min(MAX_BAR_WIDTH, ((ms(p.period_end) - ms(p.period_start)) / spanMs) * plotWidth * 0.72));

  const linePath = smoothPath(points.map((p) => ({ x: xForMs(midpointMs(p)), y: yFor(p.consumption_kwh) })));
  const lastPoint = points[points.length - 1];

  const gridFractions = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart-svg"
        role="img"
        aria-label="Solar generation versus electrical consumption by period"
      >
        {gridFractions.map((f) => {
          const v = maxVal * f;
          const y = yFor(v);
          return (
            <g key={f}>
              <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={y} y2={y} className="chart-gridline" />
              <text x={PAD_LEFT - 8} y={y} textAnchor="end" dominantBaseline="middle" className="chart-axis-label">
                {formatCompact(v)}
              </text>
            </g>
          );
        })}

        {points.map((p) => {
          const barWidth = widthFor(p);
          const x = xForMs(midpointMs(p)) - barWidth / 2;
          return (
            <rect
              key={p.period_start}
              x={x}
              y={yFor(p.generation_kwh)}
              width={barWidth}
              height={Math.max(0, yFor(0) - yFor(p.generation_kwh))}
              rx={2}
              className="chart-bar"
            />
          );
        })}

        {/* Weather-adjusted expected generation, as a dashed outline over
            the same bar — only drawn where cached irradiance covers the
            period (see solar_insights.py). Comparing the outline height
            against the filled bar is the point: it's what makes "cloudy
            month" visually distinct from "underperforming panel". */}
        {points.map((p) => {
          if (p.expected_generation_kwh === null) return null;
          const barWidth = widthFor(p);
          const x = xForMs(midpointMs(p)) - barWidth / 2;
          return (
            <rect
              key={`expected-${p.period_start}`}
              x={x}
              y={yFor(p.expected_generation_kwh)}
              width={barWidth}
              height={Math.max(0, yFor(0) - yFor(p.expected_generation_kwh))}
              rx={2}
              className="chart-bar-expected"
            />
          );
        })}

        <path d={linePath} className="chart-line" fill="none" />
        {points.map((p) => (
          <circle
            key={p.period_start}
            cx={xForMs(midpointMs(p))}
            cy={yFor(p.consumption_kwh)}
            r={3.2}
            className="chart-dot"
          />
        ))}

        {/* Newest period, marked the same way the health chart marks its
            newest reading — same visual grammar for "this is the present". */}
        <g key={`newest-${points.length}`}>
          <line
            className="chart-sweep"
            x1={xForMs(midpointMs(lastPoint))}
            x2={xForMs(midpointMs(lastPoint))}
            y1={PAD_TOP}
            y2={PAD_TOP + plotHeight}
          />
          <circle
            cx={xForMs(midpointMs(lastPoint))}
            cy={yFor(lastPoint.consumption_kwh)}
            r={3.6}
            className="chart-dot chart-dot-live"
          />
        </g>

        {points.map((p) => (
          <text
            key={p.period_start}
            x={xForMs(midpointMs(p))}
            y={HEIGHT - 8}
            textAnchor="middle"
            className="chart-axis-label"
          >
            {formatMonthLabel(p.period_start)}
          </text>
        ))}
      </svg>

      <div className="mix-legend">
        <span className="leg">
          <span className="swatch" style={{ background: "var(--solar)" }} />
          Solar generation (kWh)
        </span>
        <span className="leg">
          <span className="swatch-line" />
          Electrical consumption (kWh)
        </span>
        {points.some((p) => p.expected_generation_kwh !== null) && (
          <span className="leg">
            <span className="swatch-outline" />
            Expected (weather-adjusted)
          </span>
        )}
      </div>
    </div>
  );
}
