import { formatMonthLabel } from "../lib/dates";
import type { GenerationVsConsumptionPoint } from "../types/api";

interface GenerationChartProps {
  points: GenerationVsConsumptionPoint[];
}

const WIDTH = 720;
const HEIGHT = 260;
const PAD_LEFT = 54;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;

function formatCompact(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(value));
}

/** Real chart, not a decorative one: bars for solar generation, a line for
 * total electrical consumption (grid + diesel-equivalent + solar), plotted
 * to the same axis so the overlap — self-consumption — is visible directly
 * rather than left for the reader to compute from two separate numbers. */
export function GenerationChart({ points }: GenerationChartProps) {
  if (points.length === 0) {
    return <div className="empty-state">No solar generation data for this period.</div>;
  }

  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const maxVal = Math.max(...points.map((p) => Math.max(p.generation_kwh, p.consumption_kwh)), 1);
  const stepX = plotWidth / points.length;
  const barWidth = Math.min(30, stepX * 0.45);

  const yFor = (v: number) => PAD_TOP + plotHeight - (v / maxVal) * plotHeight;
  const xFor = (i: number) => PAD_LEFT + stepX * i + stepX / 2;

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i).toFixed(1)} ${yFor(p.consumption_kwh).toFixed(1)}`)
    .join(" ");

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

        {points.map((p, i) => (
          <rect
            key={p.period_start}
            x={xFor(i) - barWidth / 2}
            y={yFor(p.generation_kwh)}
            width={barWidth}
            height={Math.max(0, yFor(0) - yFor(p.generation_kwh))}
            rx={2}
            className="chart-bar"
          />
        ))}

        <path d={linePath} className="chart-line" fill="none" />
        {points.map((p, i) => (
          <circle key={p.period_start} cx={xFor(i)} cy={yFor(p.consumption_kwh)} r={3.2} className="chart-dot" />
        ))}

        {points.map((p, i) => (
          <text key={p.period_start} x={xFor(i)} y={HEIGHT - 8} textAnchor="middle" className="chart-axis-label">
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
      </div>
    </div>
  );
}
