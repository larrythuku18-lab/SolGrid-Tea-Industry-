import { useEffect, useMemo, useState } from "react";
import { getGenerationVsConsumption, getSolarHealth, getSolarHealthHistory } from "../api/solar";
import { ApiError } from "../api/client";
import { Banner } from "../components/Banner";
import { BatteryHistoryChart } from "../components/BatteryHistoryChart";
import { FacilitySelect } from "../components/FacilitySelect";
import { GenerationChart } from "../components/GenerationChart";
import { PageHeader } from "../components/PageHeader";
import { useFacilities } from "../hooks/useFacilities";
import { useLatestPeriod } from "../hooks/useLatestPeriod";
import { useNow } from "../hooks/useNow";
import { useSolarLive } from "../hooks/useSolarLive";
import { formatAge, formatDateTime, monthsBeforeIso, parseIsoInstant } from "../lib/dates";
import type { GenerationVsConsumptionSeries, SolarHealthPoint, SolarHealthSummary } from "../types/api";

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

const LIVE_STATUS_LABEL: Record<string, string> = {
  idle: "Not connected",
  connecting: "Connecting…",
  live: "Live",
  offline: "Reconnecting…",
};

function gaugeClass(pct: number, warnBelow: number, alertBelow: number): string {
  if (pct < alertBelow) return "gauge-fill alert";
  if (pct < warnBelow) return "gauge-fill warn";
  return "gauge-fill";
}

/** Identity of a reading for de-duplication. `ts` alone isn't enough — the
 * health feed writes several readings a day, so the values are part of the
 * key. Two readings that share a timestamp *and* both values are
 * indistinguishable anyway. */
function pointKey(p: SolarHealthPoint): string {
  return `${p.ts}|${p.battery_soc_pct}|${p.battery_soh_pct}`;
}

export function SolarPage() {
  const { facilities, isLoading: facilitiesLoading, error: facilitiesError } = useFacilities();
  const [facilityId, setFacilityId] = useState("");
  const { period } = useLatestPeriod(facilityId);

  const [series, setSeries] = useState<GenerationVsConsumptionSeries | null>(null);
  const [health, setHealth] = useState<SolarHealthSummary | null>(null);
  const [healthHistory, setHealthHistory] = useState<SolarHealthPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const rangeStart = period ? monthsBeforeIso(period.end, TRAILING_MONTHS) : undefined;
  const live = useSolarLive({ facilityId, periodStart: rangeStart, periodEnd: period?.end });
  const nowMs = useNow();

  useEffect(() => {
    if (facilities.length > 0 && !facilityId) {
      setFacilityId(facilities[0].id);
    }
  }, [facilities, facilityId]);

  useEffect(() => {
    if (!facilityId || !period || !rangeStart) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([
      getGenerationVsConsumption({ facility_id: facilityId, period_start: rangeStart, period_end: period.end }),
      getSolarHealth({ facility_id: facilityId, as_of: period.end }),
      getSolarHealthHistory({ facility_id: facilityId, period_start: rangeStart, period_end: period.end }),
    ])
      .then(([seriesResult, healthResult, historyResult]) => {
        if (cancelled) return;
        setSeries(seriesResult);
        setHealth(healthResult);
        setHealthHistory(historyResult);
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
    // `live.resyncNonce` bumps when the stream reconnects, which is the one
    // case where this page's loaded history may have a hole in it: readings
    // that landed while the stream was down were never delivered as events.
  }, [facilityId, period, rangeStart, live.resyncNonce]);

  // The REST history the page loaded, plus whatever the stream has delivered
  // since — the stream sends points, never the whole series, so the two have
  // to be merged rather than one replacing the other.
  const chartPoints = useMemo(() => {
    const merged = [...healthHistory];
    const seen = new Set(merged.map(pointKey));
    for (const point of live.newPoints) {
      const key = pointKey(point);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(point);
    }
    return merged.sort((a, b) => parseIsoInstant(a.ts).getTime() - parseIsoInstant(b.ts).getTime());
  }, [healthHistory, live.newPoints]);

  // Live overrides loaded: the stream is the newer of the two by definition,
  // and its summary is recomputed server-side whenever a reading lands.
  const effectiveSeries = live.series ?? series;
  const effectiveHealth = live.health ?? health;
  const latest = live.latest ?? health?.latest ?? null;

  const ageSeconds = useMemo(() => {
    if (!live.freshness?.latest_health_ts) return null;
    const seconds = (nowMs - parseIsoInstant(live.freshness.latest_health_ts).getTime()) / 1000;
    return Number.isFinite(seconds) ? Math.max(0, seconds) : null;
  }, [nowMs, live.freshness]);

  const totalGeneration = effectiveSeries
    ? effectiveSeries.points.reduce((sum, p) => sum + p.generation_kwh, 0)
    : 0;
  const totalConsumption = effectiveSeries
    ? effectiveSeries.points.reduce((sum, p) => sum + p.consumption_kwh, 0)
    : 0;
  const avgSelfConsumption =
    effectiveSeries && totalConsumption > 0 ? (totalGeneration / totalConsumption) * 100 : null;

  const isLive = live.status === "live";

  return (
    <>
      <PageHeader
        title="Solar"
        meta={
          <>
            Generation vs. consumption, panel/battery health — live feed over seeded readings, not real
            telemetry (see the Solar deviation note in the README)
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

      {live.status === "offline" && facilityId && (
        <Banner kind="warn">
          Live feed disconnected, retrying — showing the last data loaded
          {live.error ? ` (${live.error})` : ""}.
        </Banner>
      )}

      {isLive && live.freshness?.is_stale && (
        <Banner kind="warn">
          Live feed is connected, but the newest panel/battery reading is{" "}
          {ageSeconds !== null ? formatAge(ageSeconds) : "a long time"} old
          {live.freshness.latest_health_ts ? ` (${formatDateTime(live.freshness.latest_health_ts)})` : ""} — the
          site has stopped reporting. This view is showing its last known state, not a quiet site.
        </Banner>
      )}

      {effectiveSeries && effectiveSeries.install_capacity_kw === null && (
        <Banner kind="warn">
          No install_capacity_kw on file for this facility — no panels contracted yet.
        </Banner>
      )}

      {effectiveSeries && (
        <>
          <section className="tiles">
            <div className="tile">
              <div className="tile-label">Install capacity</div>
              <div className="tile-num mono">
                {effectiveSeries.install_capacity_kw !== null
                  ? numFormatter.format(effectiveSeries.install_capacity_kw)
                  : "—"}{" "}
                <small>kW</small>
              </div>
              <div className="tile-foot">nameplate, if contracted</div>
            </div>
            <div className="tile">
              <div className="tile-label">Generation, trailing {TRAILING_MONTHS}mo</div>
              <div key={`gen-${totalGeneration}`} className="tile-num mono value-flash">
                {numFormatter.format(totalGeneration)} <small>kWh</small>
              </div>
              <div className="tile-foot">solar only</div>
            </div>
            <div className="tile">
              <div className="tile-label">Self-consumption</div>
              <div
                key={`self-${avgSelfConsumption}`}
                className="tile-num mono value-flash"
              >
                {avgSelfConsumption !== null ? `${numFormatter.format(avgSelfConsumption)}%` : "—"}
              </div>
              <div className="tile-foot">share of electrical load covered by solar</div>
            </div>
            <div className="tile">
              <div className="tile-label">Battery state of health</div>
              <div
                key={`soh-${latest?.battery_soh_pct ?? "none"}`}
                className="tile-num mono value-flash"
              >
                {latest?.battery_soh_pct !== null && latest?.battery_soh_pct !== undefined
                  ? `${numFormatter.format(latest.battery_soh_pct)}%`
                  : "—"}
              </div>
              <div className="tile-foot">
                {effectiveHealth?.battery_soh_trend_pct !== null &&
                effectiveHealth?.battery_soh_trend_pct !== undefined
                  ? `${effectiveHealth.battery_soh_trend_pct >= 0 ? "+" : ""}${numFormatter.format(effectiveHealth.battery_soh_trend_pct)} pts over window on file`
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
              <GenerationChart
                points={effectiveSeries.points}
                domainStart={rangeStart}
                domainEnd={period?.end}
              />
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div className="panel-h-left">
                <span className="panel-title">Panel &amp; battery health</span>
              </div>
              <span
                className={`live-badge ${live.status}`}
                title={
                  "Server-sent events over seeded solar_health_reading rows — real rows arriving in real time, but no ESP32 hardware yet (README deviation #9)"
                }
              >
                <span className="live-dot" />
                {LIVE_STATUS_LABEL[live.status]}
                {isLive && ageSeconds !== null && (
                  <>
                    {" · "}
                    {live.freshness?.is_stale ? "last reading" : "updated"} {formatAge(ageSeconds)} ago
                  </>
                )}
              </span>
            </div>

            {!latest ? (
              <div className="empty-state">
                {isLoading ? "Loading…" : "No health telemetry on file for this facility yet."}
              </div>
            ) : (
              <>
                <div className="panel-body" style={{ paddingBottom: 0 }}>
                  <BatteryHistoryChart
                    points={chartPoints}
                    domainStart={rangeStart}
                    domainEnd={period?.end}
                  />
                  <div className="panel-note" style={{ marginTop: 10 }}>
                    Last recorded reading: <b>{formatDateTime(latest.ts)}</b>
                    {ageSeconds !== null && <> ({formatAge(ageSeconds)} ago)</>}
                  </div>
                </div>

                <div className="health-grid">
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Battery state of charge</span>
                      <span
                        key={`soc-val-${latest.battery_soc_pct ?? "none"}`}
                        className="gauge-val value-flash"
                      >
                        {latest.battery_soc_pct !== null ? `${latest.battery_soc_pct.toFixed(1)}%` : "—"}
                      </span>
                    </div>
                    <div className="gauge-track">
                      <div
                        className={gaugeClass(latest.battery_soc_pct ?? 100, 30, 15)}
                        style={{ width: `${latest.battery_soc_pct ?? 0}%` }}
                      />
                    </div>
                  </div>
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Battery state of health</span>
                      <span
                        key={`soh-val-${latest.battery_soh_pct ?? "none"}`}
                        className="gauge-val value-flash"
                      >
                        {latest.battery_soh_pct !== null ? `${latest.battery_soh_pct.toFixed(1)}%` : "—"}
                      </span>
                    </div>
                    <div className="gauge-track">
                      <div
                        className={gaugeClass(latest.battery_soh_pct ?? 100, 85, 70)}
                        style={{ width: `${latest.battery_soh_pct ?? 0}%` }}
                      />
                    </div>
                  </div>
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Panel status</span>
                      <span className={STATUS_PILL_CLASS[latest.panel_status]}>
                        {STATUS_LABEL[latest.panel_status]}
                      </span>
                    </div>
                  </div>
                  <div className="gauge">
                    <div className="gauge-label">
                      <span>Battery status</span>
                      <span className={STATUS_PILL_CLASS[latest.battery_status]}>
                        {STATUS_LABEL[latest.battery_status]}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="insight-list">
                  {effectiveHealth?.insights.map((insight, i) => (
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
