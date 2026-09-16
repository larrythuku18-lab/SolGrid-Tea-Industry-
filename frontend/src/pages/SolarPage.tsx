import { useEffect, useState } from "react";
import { getGenerationVsConsumption, getSolarHealth } from "../api/solar";
import { ApiError } from "../api/client";
import { Banner } from "../components/Banner";
import { FacilitySelect } from "../components/FacilitySelect";
import { GenerationChart } from "../components/GenerationChart";
import { PageHeader } from "../components/PageHeader";
import { useFacilities } from "../hooks/useFacilities";
import { useLatestPeriod } from "../hooks/useLatestPeriod";
import { monthsBeforeIso } from "../lib/dates";
import type { GenerationVsConsumptionSeries, SolarHealthSummary } from "../types/api";

const numFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 1 });
const TRAILING_MONTHS = 8;

const STATUS_PILL_CLASS: Record<string, string> = {
  normal: "pill",
  underperforming: "pill warn",
  degraded: "pill warn",
  fault: "pill alert",
};

const STATUS_LABEL: Record<string, string> = {
  normal: "Normal",
  underperforming: "Underperforming",
  degraded: "Degraded",
  fault: "Fault",
};

function gaugeClass(pct: number, warnBelow: number, alertBelow: number): string {
  if (pct < alertBelow) return "gauge-fill alert";
  if (pct < warnBelow) return "gauge-fill warn";
  return "gauge-fill";
}

export function SolarPage() {
  const { facilities, isLoading: facilitiesLoading, error: facilitiesError } = useFacilities();
  const [facilityId, setFacilityId] = useState("");
  const { period } = useLatestPeriod(facilityId);

  const [series, setSeries] = useState<GenerationVsConsumptionSeries | null>(null);
  const [health, setHealth] = useState<SolarHealthSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (facilities.length > 0 && !facilityId) {
      setFacilityId(facilities[0].id);
    }
  }, [facilities, facilityId]);

  useEffect(() => {
    if (!facilityId || !period) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const rangeStart = monthsBeforeIso(period.end, TRAILING_MONTHS);

    Promise.all([
      getGenerationVsConsumption({ facility_id: facilityId, period_start: rangeStart, period_end: period.end }),
      getSolarHealth({ facility_id: facilityId, as_of: period.end }),
    ])
      .then(([seriesResult, healthResult]) => {
        if (cancelled) return;
        setSeries(seriesResult);
        setHealth(healthResult);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load solar data.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [facilityId, period]);

  const totalGeneration = series ? series.points.reduce((sum, p) => sum + p.generation_kwh, 0) : 0;
  const totalConsumption = series ? series.points.reduce((sum, p) => sum + p.consumption_kwh, 0) : 0;
  const avgSelfConsumption =
    series && totalConsumption > 0 ? (totalGeneration / totalConsumption) * 100 : null;

  return (
    <>
      <PageHeader
        title="Solar"
        meta={
          <>
            Generation vs. consumption, panel/battery health — presentation data, not live telemetry
            (see the Solar deviation note in the README)
          </>
        }
        right={
          facilities.length > 0 && (
            <FacilitySelect facilities={facilities} value={facilityId} onChange={setFacilityId} />
          )
        }
      />

      {facilitiesError && <Banner kind="error">{facilitiesError}</Banner>}
      {error && <Banner kind="error">{error}</Banner>}
      {!facilitiesLoading && facilities.length === 0 && (
        <Banner kind="warn">No facilities yet.</Banner>
      )}

      {series && series.install_capacity_kw === null && (
        <Banner kind="warn">
          No install_capacity_kw on file for this facility — no panels contracted yet.
        </Banner>
      )}

      {series && (
        <>
          <section className="tiles">
            <div className="tile">
              <div className="tile-label">Install capacity</div>
              <div className="tile-num mono">
                {series.install_capacity_kw !== null ? numFormatter.format(series.install_capacity_kw) : "—"}{" "}
                <small>kW</small>
              </div>
              <div className="tile-foot">nameplate, if contracted</div>
            </div>
            <div className="tile">
              <div className="tile-label">Generation, trailing {TRAILING_MONTHS}mo</div>
              <div className="tile-num mono">
                {numFormatter.format(totalGeneration)} <small>kWh</small>
              </div>
              <div className="tile-foot">solar only</div>
            </div>
            <div className="tile">
              <div className="tile-label">Self-consumption</div>
              <div className="tile-num mono">
                {avgSelfConsumption !== null ? `${numFormatter.format(avgSelfConsumption)}%` : "—"}
              </div>
              <div className="tile-foot">share of electrical load covered by solar</div>
            </div>
            <div className="tile">
              <div className="tile-label">Battery state of health</div>
              <div className="tile-num mono">
                {health?.latest?.battery_soh_pct !== null && health?.latest?.battery_soh_pct !== undefined
                  ? `${numFormatter.format(health.latest.battery_soh_pct)}%`
                  : "—"}
              </div>
              <div className="tile-foot">
                {health?.battery_soh_trend_pct !== null && health?.battery_soh_trend_pct !== undefined
                  ? `${health.battery_soh_trend_pct >= 0 ? "+" : ""}${numFormatter.format(health.battery_soh_trend_pct)} pts over window on file`
                  : "no trend yet"}
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div className="panel-h-left">
                <span className="panel-title">Generation vs. consumption</span>
              </div>
              <span className="panel-note">trailing {TRAILING_MONTHS} months on file</span>
            </div>
            <div className="panel-body">
              <GenerationChart points={series.points} />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div className="panel-h-left">
                <span className="panel-title">Panel &amp; battery health</span>
              </div>
              {health?.latest && (
                <span className="panel-note">
                  as of <b>{health.latest.ts}</b>
                </span>
              )}
            </div>

            {!health?.latest ? (
              <div className="empty-state">
                {isLoading ? "Loading…" : "No health telemetry on file for this facility yet."}
              </div>
            ) : (
              <>
                <div className="health-grid">
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Battery state of charge</span>
                      <span className="gauge-val">
                        {health.latest.battery_soc_pct !== null ? `${health.latest.battery_soc_pct.toFixed(0)}%` : "—"}
                      </span>
                    </div>
                    <div className="gauge-track">
                      <div
                        className={gaugeClass(health.latest.battery_soc_pct ?? 100, 30, 15)}
                        style={{ width: `${health.latest.battery_soc_pct ?? 0}%` }}
                      />
                    </div>
                  </div>
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Battery state of health</span>
                      <span className="gauge-val">
                        {health.latest.battery_soh_pct !== null ? `${health.latest.battery_soh_pct.toFixed(0)}%` : "—"}
                      </span>
                    </div>
                    <div className="gauge-track">
                      <div
                        className={gaugeClass(health.latest.battery_soh_pct ?? 100, 85, 70)}
                        style={{ width: `${health.latest.battery_soh_pct ?? 0}%` }}
                      />
                    </div>
                  </div>
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Panel status</span>
                      <span className={STATUS_PILL_CLASS[health.latest.panel_status]}>
                        {STATUS_LABEL[health.latest.panel_status]}
                      </span>
                    </div>
                  </div>
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Battery status</span>
                      <span className={STATUS_PILL_CLASS[health.latest.battery_status]}>
                        {STATUS_LABEL[health.latest.battery_status]}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="insight-list">
                  {health.insights.map((insight, i) => (
                    <div key={i} className={`insight ${insight.severity}`}>
                      <span className="insight-dot" />
                      <span>{insight.message}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
