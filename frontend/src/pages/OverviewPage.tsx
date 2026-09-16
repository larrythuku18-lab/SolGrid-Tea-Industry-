import { useEffect, useState } from "react";
import { getBenchmark } from "../api/benchmark";
import { listEnergyReadings } from "../api/ledger";
import { Banner } from "../components/Banner";
import { FacilitySelect } from "../components/FacilitySelect";
import { PageHeader } from "../components/PageHeader";
import { useFacilities } from "../hooks/useFacilities";
import { useLatestPeriod } from "../hooks/useLatestPeriod";
import { READING_TYPE_COLOR, READING_TYPE_LABEL } from "../lib/readingTypes";
import type { BenchmarkResult, EnergyReading } from "../types/api";
import { ApiError } from "../api/client";

const kesFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });
const numFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 1 });

export function OverviewPage() {
  const { facilities, isLoading: facilitiesLoading, error: facilitiesError } = useFacilities();
  const [facilityId, setFacilityId] = useState("");
  const { period } = useLatestPeriod(facilityId);

  const [benchmark, setBenchmark] = useState<BenchmarkResult | null>(null);
  const [recentReadings, setRecentReadings] = useState<EnergyReading[]>([]);
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

    Promise.all([
      getBenchmark({ facility_id: facilityId, period_start: period.start, period_end: period.end }),
      listEnergyReadings({ facility_id: facilityId }),
    ])
      .then(([benchmarkResult, readings]) => {
        if (cancelled) return;
        setBenchmark(benchmarkResult);
        setRecentReadings(readings.slice(0, 8));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load overview data.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [facilityId, period]);

  const mixEntries = benchmark ? Object.entries(benchmark.energy_mix_pct) : [];

  return (
    <>
      <PageHeader
        title="Overview"
        meta={
          <>
            {facilities.length} facilit{facilities.length === 1 ? "y" : "ies"}
            {period && (
              <>
                {" "}
                · latest period on file <b>{period.start}</b> to <b>{period.end}</b>
              </>
            )}
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
        <Banner kind="warn">
          No facilities yet. An admin can add one — see the Ledger page once a facility exists.
        </Banner>
      )}

      {benchmark && (
        <>
          <section className="tiles">
            <div className="tile">
              <div className="tile-label">Tea produced</div>
              <div className="tile-num mono">
                {numFormatter.format(benchmark.total_made_tea_kg)} <small>kg</small>
              </div>
              <div className="tile-foot">latest period on file</div>
            </div>
            <div className="tile">
              <div className="tile-label">Energy cost</div>
              <div className="tile-num mono">KES {kesFormatter.format(benchmark.total_cost_kes)}</div>
              <div className="tile-foot">grid + diesel + fuelwood</div>
            </div>
            <div className="tile">
              <div className="tile-label">Cost per kg tea</div>
              <div className="tile-num mono">
                {benchmark.cost_per_kg_tea_kes !== null
                  ? `KES ${numFormatter.format(benchmark.cost_per_kg_tea_kes)}`
                  : "—"}
              </div>
              <div className="tile-foot">energy cost only</div>
            </div>
            <div className="tile">
              <div className="tile-label">kWh per kg tea</div>
              <div className="tile-num mono">
                {benchmark.kwh_per_kg_tea !== null ? numFormatter.format(benchmark.kwh_per_kg_tea) : "—"}
              </div>
              <div className="tile-foot">energy intensity</div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div className="panel-h-left">
                <span className="panel-title">Energy mix</span>
              </div>
              <span className="panel-note">
                total <b>{numFormatter.format(benchmark.total_energy_kwh)} kWh</b>
              </span>
            </div>
            <div className="panel-body">
              {mixEntries.length === 0 ? (
                <div className="empty-state">No energy readings with a known conversion factor yet.</div>
              ) : (
                <>
                  <div className="mix-bar">
                    {mixEntries.map(([type, pct]) => (
                      <div
                        key={type}
                        style={{ width: `${pct}%`, background: READING_TYPE_COLOR[type] ?? "var(--ink-faint)" }}
                      />
                    ))}
                  </div>
                  <div className="mix-legend">
                    {mixEntries.map(([type, pct]) => (
                      <span className="leg" key={type}>
                        <span
                          className="swatch"
                          style={{ background: READING_TYPE_COLOR[type] ?? "var(--ink-faint)" }}
                        />
                        {READING_TYPE_LABEL[type as keyof typeof READING_TYPE_LABEL] ?? type} ·{" "}
                        {numFormatter.format(pct)}%
                      </span>
                    ))}
                  </div>
                </>
              )}
              {benchmark.missing_energy_content_factors.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <Banner kind="warn">
                    No energy-content factor on file for:{" "}
                    {benchmark.missing_energy_content_factors.join(", ")} — those readings are excluded
                    from the mix above.
                  </Banner>
                </div>
              )}
            </div>
          </section>
        </>
      )}

      <section className="panel">
        <div className="panel-head">
          <div className="panel-h-left">
            <span className="panel-title">Recent ledger entries</span>
          </div>
        </div>
        {recentReadings.length === 0 ? (
          <div className="empty-state">{isLoading ? "Loading…" : "No energy readings logged yet."}</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Period</th>
                  <th>Quantity</th>
                  <th>Cost (KES)</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {recentReadings.map((r) => (
                  <tr key={r.id}>
                    <td>{READING_TYPE_LABEL[r.reading_type]}</td>
                    <td className="mono">
                      {r.period_start} → {r.period_end}
                    </td>
                    <td className="mono">
                      {numFormatter.format(r.quantity)} {r.unit}
                    </td>
                    <td className="mono">{r.cost_kes !== null ? kesFormatter.format(r.cost_kes) : "—"}</td>
                    <td>
                      <span className="tag">{r.source_channel}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
