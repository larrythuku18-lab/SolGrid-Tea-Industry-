import { useEffect, useState, type FormEvent } from "react";
import { getBenchmark } from "../api/benchmark";
import { ApiError } from "../api/client";
import { Banner } from "../components/Banner";
import { FacilitySelect } from "../components/FacilitySelect";
import { PageHeader } from "../components/PageHeader";
import { useFacilities } from "../hooks/useFacilities";
import { currentMonthRange } from "../lib/dates";
import { READING_TYPE_COLOR, READING_TYPE_LABEL } from "../lib/readingTypes";
import type { BenchmarkResult } from "../types/api";

const numFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 2 });
const kesFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });

export function BenchmarkPage() {
  const { facilities, isLoading: facilitiesLoading, error: facilitiesError } = useFacilities();
  const defaultRange = currentMonthRange();

  const [facilityId, setFacilityId] = useState("");
  const [periodStart, setPeriodStart] = useState(defaultRange.start);
  const [periodEnd, setPeriodEnd] = useState(defaultRange.end);
  const [result, setResult] = useState<BenchmarkResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (facilities.length > 0 && !facilityId) setFacilityId(facilities[0].id);
  }, [facilities, facilityId]);

  async function runBenchmark(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const data = await getBenchmark({ facility_id: facilityId, period_start: periodStart, period_end: periodEnd });
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to compute benchmark.");
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  }

  const mixEntries = result ? Object.entries(result.energy_mix_pct) : [];

  return (
    <>
      <PageHeader title="Benchmark" meta="Cost per kg tea, energy intensity, and energy mix for a period" />

      {facilitiesError && <Banner kind="error">{facilitiesError}</Banner>}
      {!facilitiesLoading && facilities.length === 0 && <Banner kind="warn">No facilities yet.</Banner>}

      {facilities.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <span className="panel-title">Query</span>
          </div>
          <form onSubmit={runBenchmark}>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="bm-facility">Facility</label>
                <FacilitySelect facilities={facilities} value={facilityId} onChange={setFacilityId} id="bm-facility" />
              </div>
              <div className="field">
                <label htmlFor="bm-start">Period start</label>
                <input id="bm-start" type="date" required value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="bm-end">Period end</label>
                <input id="bm-end" type="date" required value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn btn-primary" disabled={isLoading}>
                {isLoading ? "Computing…" : "Run benchmark"}
              </button>
            </div>
          </form>
        </section>
      )}

      {error && <Banner kind="error">{error}</Banner>}

      {result && (
        <>
          <section className="panel">
            <div className="panel-head">
              <span className="panel-title">Results</span>
              <span className="panel-note">
                {result.period_start} → {result.period_end}
              </span>
            </div>
            <div className="metric-grid">
              <div className="metric">
                <span className="metric-label">Tea produced</span>
                <span className="metric-val mono">
                  {numFormatter.format(result.total_made_tea_kg)}
                  <span className="u">kg</span>
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Total energy cost</span>
                <span className="metric-val mono">KES {kesFormatter.format(result.total_cost_kes)}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Total energy</span>
                <span className="metric-val mono">
                  {numFormatter.format(result.total_energy_kwh)}
                  <span className="u">kWh</span>
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Cost per kg tea</span>
                <span className="metric-val mono">
                  {result.cost_per_kg_tea_kes !== null ? `KES ${numFormatter.format(result.cost_per_kg_tea_kes)}` : "—"}
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">kWh per kg tea</span>
                <span className="metric-val mono">
                  {result.kwh_per_kg_tea !== null ? numFormatter.format(result.kwh_per_kg_tea) : "—"}
                </span>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <span className="panel-title">Energy mix</span>
            </div>
            <div className="panel-body">
              {mixEntries.length === 0 ? (
                <div className="empty-state">No readings with a known energy-content factor for this period.</div>
              ) : (
                <>
                  <div className="mix-bar">
                    {mixEntries.map(([type, pct]) => (
                      <div key={type} style={{ width: `${pct}%`, background: READING_TYPE_COLOR[type] ?? "var(--ink-faint)" }} />
                    ))}
                  </div>
                  <div className="mix-legend">
                    {mixEntries.map(([type, pct]) => (
                      <span className="leg" key={type}>
                        <span className="swatch" style={{ background: READING_TYPE_COLOR[type] ?? "var(--ink-faint)" }} />
                        {READING_TYPE_LABEL[type as keyof typeof READING_TYPE_LABEL] ?? type} · {numFormatter.format(pct)}%
                      </span>
                    ))}
                  </div>
                </>
              )}
              {result.missing_energy_content_factors.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <Banner kind="warn">
                    Excluded from totals (no energy-content factor on file): {result.missing_energy_content_factors.join(", ")}
                  </Banner>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}
