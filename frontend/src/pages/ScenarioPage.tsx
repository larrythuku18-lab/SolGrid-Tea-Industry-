import { useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { runScenario } from "../api/scenario";
import { Banner } from "../components/Banner";
import { FacilitySelect } from "../components/FacilitySelect";
import { PageHeader } from "../components/PageHeader";
import { useAuth } from "../auth/AuthContext";
import { useFacilities } from "../hooks/useFacilities";
import type { FinancingMode, ScenarioResult } from "../types/api";

const numFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 2 });
const kesFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });
const pctFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 2 });

interface FormState {
  facilityId: string;
  financingMode: FinancingMode;
  targetSolarKw: string;
  gridTariff: string;
  ppaRate: string;
  capex: string;
  daytimeCoincidence: string;
  solarCapacityFactor: string;
  baselineGridKwh: string;
  baselineElectricalKwh: string;
  baselineTotalKwh: string;
}

const initialForm: FormState = {
  facilityId: "",
  financingMode: "capex",
  targetSolarKw: "",
  gridTariff: "25",
  ppaRate: "",
  capex: "",
  daytimeCoincidence: "0.50",
  solarCapacityFactor: "0.20",
  baselineGridKwh: "",
  baselineElectricalKwh: "",
  baselineTotalKwh: "",
};

export function ScenarioPage() {
  const { me } = useAuth();
  const canRun = me?.role === "admin" || me?.role === "operator";
  const { facilities, isLoading: facilitiesLoading, error: facilitiesError } = useFacilities();

  const [form, setForm] = useState<FormState>(initialForm);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (facilities.length > 0 && !form.facilityId) {
      setForm((f) => ({ ...f, facilityId: facilities[0].id }));
    }
  }, [facilities, form.facilityId]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const data = await runScenario({
        facility_id: form.facilityId,
        financing_mode: form.financingMode,
        target_solar_kw: Number(form.targetSolarKw),
        grid_tariff_kes_per_kwh: Number(form.gridTariff),
        ppa_rate_kes_per_kwh: form.financingMode === "ppa" ? Number(form.ppaRate) : null,
        capex_kes: form.financingMode === "capex" ? Number(form.capex) : null,
        daytime_coincidence_factor: Number(form.daytimeCoincidence),
        solar_capacity_factor: Number(form.solarCapacityFactor),
        baseline_annual_grid_kwh: Number(form.baselineGridKwh),
        baseline_annual_electrical_kwh: Number(form.baselineElectricalKwh),
        baseline_annual_total_energy_kwh: Number(form.baselineTotalKwh),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to run scenario.");
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader title="Scenarios" meta="Pure-solar what-if: addressable share, savings, payback, avoided emissions" />

      {facilitiesError && <Banner kind="error">{facilitiesError}</Banner>}
      {!facilitiesLoading && facilities.length === 0 && <Banner kind="warn">No facilities yet.</Banner>}
      {!canRun && facilities.length > 0 && (
        <Banner kind="warn">Your role can view scenarios but not run new ones — ask an admin or operator.</Banner>
      )}

      {facilities.length > 0 && canRun && (
        <section className="panel">
          <div className="panel-head">
            <span className="panel-title">Assumptions</span>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="sc-facility">Facility</label>
                <FacilitySelect facilities={facilities} value={form.facilityId} onChange={(v) => set("facilityId", v)} id="sc-facility" />
              </div>
              <div className="field">
                <label htmlFor="sc-financing">Financing mode</label>
                <select
                  id="sc-financing"
                  value={form.financingMode}
                  onChange={(e) => set("financingMode", e.target.value as FinancingMode)}
                >
                  <option value="capex">Capex (self-financed)</option>
                  <option value="ppa">PPA</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="sc-kw">Target solar (kW)</label>
                <input id="sc-kw" type="number" step="any" min="0" required value={form.targetSolarKw} onChange={(e) => set("targetSolarKw", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="sc-tariff">Grid tariff (KES/kWh)</label>
                <input id="sc-tariff" type="number" step="any" min="0" required value={form.gridTariff} onChange={(e) => set("gridTariff", e.target.value)} />
              </div>
              {form.financingMode === "ppa" ? (
                <div className="field">
                  <label htmlFor="sc-ppa">PPA rate (KES/kWh)</label>
                  <input id="sc-ppa" type="number" step="any" min="0" required value={form.ppaRate} onChange={(e) => set("ppaRate", e.target.value)} />
                </div>
              ) : (
                <div className="field">
                  <label htmlFor="sc-capex">Capex (KES)</label>
                  <input id="sc-capex" type="number" step="any" min="0" required value={form.capex} onChange={(e) => set("capex", e.target.value)} />
                </div>
              )}
              <div className="field">
                <label htmlFor="sc-coincidence">Daytime coincidence factor</label>
                <input
                  id="sc-coincidence"
                  type="number"
                  step="any"
                  min="0"
                  max="1"
                  required
                  value={form.daytimeCoincidence}
                  onChange={(e) => set("daytimeCoincidence", e.target.value)}
                />
                <span className="field-hint">Share of electrical demand that falls in daylight hours</span>
              </div>
              <div className="field">
                <label htmlFor="sc-capfactor">Solar capacity factor</label>
                <input
                  id="sc-capfactor"
                  type="number"
                  step="any"
                  min="0"
                  max="0.35"
                  required
                  value={form.solarCapacityFactor}
                  onChange={(e) => set("solarCapacityFactor", e.target.value)}
                />
                <span className="field-hint">No safe platform default — verify for this site</span>
              </div>
              <div className="field">
                <label htmlFor="sc-grid-kwh">Baseline grid (kWh/yr)</label>
                <input id="sc-grid-kwh" type="number" step="any" min="0" required value={form.baselineGridKwh} onChange={(e) => set("baselineGridKwh", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="sc-elec-kwh">Baseline electrical (kWh/yr)</label>
                <input
                  id="sc-elec-kwh"
                  type="number"
                  step="any"
                  min="0"
                  required
                  value={form.baselineElectricalKwh}
                  onChange={(e) => set("baselineElectricalKwh", e.target.value)}
                />
                <span className="field-hint">Grid + any electrical diesel backup</span>
              </div>
              <div className="field">
                <label htmlFor="sc-total-kwh">Baseline total energy (kWh-eq/yr)</label>
                <input
                  id="sc-total-kwh"
                  type="number"
                  step="any"
                  min="0"
                  required
                  value={form.baselineTotalKwh}
                  onChange={(e) => set("baselineTotalKwh", e.target.value)}
                />
                <span className="field-hint">Electrical + thermal (fuelwood etc.)</span>
              </div>
            </div>
            <div className="form-actions">
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? "Running…" : "Run scenario"}
              </button>
            </div>
          </form>
        </section>
      )}

      {error && <Banner kind="error">{error}</Banner>}

      {result && (
        <section className="panel">
          <div className="panel-head">
            <span className="panel-title">Result</span>
          </div>
          <div className="metric-grid">
            <div className="metric">
              <span className="metric-label">Solar generation</span>
              <span className="metric-val mono">
                {numFormatter.format(result.solar_annual_generation_kwh)}
                <span className="u">kWh/yr</span>
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Addressable</span>
              <span className="metric-val mono">
                {numFormatter.format(result.addressable_kwh)}
                <span className="u">kWh/yr</span>
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Share of electrical demand</span>
              <span className="metric-val mono">{pctFormatter.format(result.addressable_electrical_share_pct)}%</span>
            </div>
            <div className="metric">
              <span className="metric-label">Share of total energy</span>
              <span className="metric-val mono">{pctFormatter.format(result.addressable_of_total_energy_pct)}%</span>
            </div>
            <div className="metric">
              <span className="metric-label">Annual savings</span>
              <span className="metric-val mono">KES {kesFormatter.format(result.annual_savings_kes)}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Payback</span>
              <span className="metric-val mono">
                {result.payback_years !== null ? `${numFormatter.format(result.payback_years)} yrs` : "n/a (PPA)"}
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Grid emissions avoided</span>
              <span className="metric-val mono">
                {numFormatter.format(result.emissions_avoided_grid_tco2)}
                <span className="u">tCO₂/yr</span>
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Fuelwood reduction</span>
              <span className="metric-val mono">
                {numFormatter.format(result.fuelwood_reduction_m3)}
                <span className="u">m³ (n/a — solar-only)</span>
              </span>
            </div>
          </div>
          <div style={{ padding: "0 18px 18px" }}>
            <Banner kind="warn">{result.grid_emission_factor_methodology_note}</Banner>
          </div>
        </section>
      )}
    </>
  );
}
