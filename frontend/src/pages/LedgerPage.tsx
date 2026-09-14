import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { createFacility } from "../api/facilities";
import { createEnergyReading, createProductionRecord, listEnergyReadings, listProductionRecords } from "../api/ledger";
import { Banner } from "../components/Banner";
import { FacilitySelect } from "../components/FacilitySelect";
import { PageHeader } from "../components/PageHeader";
import { useFacilities } from "../hooks/useFacilities";
import { READING_TYPE_LABEL, READING_TYPE_UNIT } from "../lib/readingTypes";
import type { EnergyReading, ProductionRecord, ReadingType } from "../types/api";

const numFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 1 });
const kesFormatter = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });

const READING_TYPES: ReadingType[] = ["grid_electricity", "diesel", "fuelwood", "solar_generation"];

export function LedgerPage() {
  const { me } = useAuth();
  const canWrite = me?.role === "admin" || me?.role === "operator";
  const canAddFacility = me?.role === "admin";

  const { facilities, isLoading: facilitiesLoading, error: facilitiesError, reload: reloadFacilities } =
    useFacilities();
  const [facilityId, setFacilityId] = useState("");

  useEffect(() => {
    if (facilities.length > 0 && !facilityId) setFacilityId(facilities[0].id);
  }, [facilities, facilityId]);

  const [readings, setReadings] = useState<EnergyReading[]>([]);
  const [production, setProduction] = useState<ProductionRecord[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!facilityId) return;
    let cancelled = false;
    setListError(null);
    Promise.all([listEnergyReadings({ facility_id: facilityId }), listProductionRecords({ facility_id: facilityId })])
      .then(([r, p]) => {
        if (cancelled) return;
        setReadings(r);
        setProduction(p);
      })
      .catch((err: unknown) => {
        if (!cancelled) setListError(err instanceof Error ? err.message : "Failed to load ledger.");
      });
    return () => {
      cancelled = true;
    };
  }, [facilityId, reloadKey]);

  return (
    <>
      <PageHeader
        title="Ledger"
        meta="Tier-4 ingestion — web form channel"
        right={
          facilities.length > 0 && (
            <FacilitySelect facilities={facilities} value={facilityId} onChange={setFacilityId} />
          )
        }
      />

      {facilitiesError && <Banner kind="error">{facilitiesError}</Banner>}
      {listError && <Banner kind="error">{listError}</Banner>}

      {!facilitiesLoading && facilities.length === 0 && !canAddFacility && (
        <Banner kind="warn">No facilities yet. Ask an admin to add one.</Banner>
      )}

      {canAddFacility && <AddFacilityPanel onCreated={reloadFacilities} />}

      {facilityId && (
        <>
          {canWrite && (
            <div className="two-col">
              <EnergyReadingForm facilityId={facilityId} onCreated={() => setReloadKey((k) => k + 1)} />
              <ProductionRecordForm facilityId={facilityId} onCreated={() => setReloadKey((k) => k + 1)} />
            </div>
          )}

          <section className="panel">
            <div className="panel-head">
              <span className="panel-title">Energy readings</span>
              <span className="panel-note">{readings.length} on file</span>
            </div>
            {readings.length === 0 ? (
              <div className="empty-state">No energy readings logged yet.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Period</th>
                      <th>Quantity</th>
                      <th>Cost (KES)</th>
                      <th>Moisture</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {readings.map((r) => (
                      <tr key={r.id}>
                        <td>{READING_TYPE_LABEL[r.reading_type]}</td>
                        <td className="mono">
                          {r.period_start} → {r.period_end}
                        </td>
                        <td className="mono">
                          {numFormatter.format(r.quantity)} {r.unit}
                        </td>
                        <td className="mono">{r.cost_kes !== null ? kesFormatter.format(r.cost_kes) : "—"}</td>
                        <td className="mono">{r.moisture_pct !== null ? `${r.moisture_pct}%` : "—"}</td>
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

          <section className="panel">
            <div className="panel-head">
              <span className="panel-title">Production records</span>
              <span className="panel-note">{production.length} on file</span>
            </div>
            {production.length === 0 ? (
              <div className="empty-state">No production records logged yet.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Made tea (kg)</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {production.map((p) => (
                      <tr key={p.id}>
                        <td className="mono">
                          {p.period_start} → {p.period_end}
                        </td>
                        <td className="mono">{numFormatter.format(p.made_tea_kg)}</td>
                        <td>
                          <span className="tag">{p.source}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}

function AddFacilityPanel({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [county, setCounty] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) {
    return (
      <button type="button" className="btn btn-secondary" style={{ marginBottom: 18 }} onClick={() => setOpen(true)}>
        + Add facility
      </button>
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createFacility({ name, county: county || undefined });
      setName("");
      setCounty("");
      setOpen(false);
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create facility.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <span className="panel-title">Add facility</span>
      </div>
      {error && (
        <div style={{ padding: "0 18px" }}>
          <Banner kind="error">{error}</Banner>
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="fac-name">Name</label>
            <input id="fac-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="fac-county">County</label>
            <input id="fac-county" value={county} onChange={(e) => setCounty(e.target.value)} />
          </div>
        </div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save facility"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}

function EnergyReadingForm({ facilityId, onCreated }: { facilityId: string; onCreated: () => void }) {
  const [readingType, setReadingType] = useState<ReadingType>("grid_electricity");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [quantity, setQuantity] = useState("");
  const [cost, setCost] = useState("");
  const [moisture, setMoisture] = useState("");
  const [sourcePlantation, setSourcePlantation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const isFuelwood = readingType === "fuelwood";
  const isSolar = readingType === "solar_generation";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await createEnergyReading({
        facility_id: facilityId,
        reading_type: readingType,
        period_start: periodStart,
        period_end: periodEnd,
        quantity: Number(quantity),
        unit: READING_TYPE_UNIT[readingType],
        cost_kes: isSolar || cost === "" ? null : Number(cost),
        moisture_pct: isFuelwood && moisture !== "" ? Number(moisture) : null,
        source_plantation: isFuelwood && sourcePlantation !== "" ? sourcePlantation : null,
        source_channel: "manual",
      });
      setQuantity("");
      setCost("");
      setMoisture("");
      setSourcePlantation("");
      setSuccess(true);
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save reading.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <span className="panel-title">Log energy reading</span>
      </div>
      {error && (
        <div style={{ padding: "0 18px" }}>
          <Banner kind="error">{error}</Banner>
        </div>
      )}
      {success && (
        <div style={{ padding: "0 18px" }}>
          <Banner kind="success">Reading saved.</Banner>
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="reading-type">Type</label>
            <select id="reading-type" value={readingType} onChange={(e) => setReadingType(e.target.value as ReadingType)}>
              {READING_TYPES.map((t) => (
                <option key={t} value={t}>
                  {READING_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="period-start">Period start</label>
            <input id="period-start" type="date" required value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="period-end">Period end</label>
            <input id="period-end" type="date" required value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="quantity">Quantity ({READING_TYPE_UNIT[readingType]})</label>
            <input
              id="quantity"
              type="number"
              step="any"
              min="0"
              required
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </div>
          {!isSolar && (
            <div className="field">
              <label htmlFor="cost">Cost (KES)</label>
              <input id="cost" type="number" step="any" min="0" value={cost} onChange={(e) => setCost(e.target.value)} />
            </div>
          )}
          {isFuelwood && (
            <>
              <div className="field">
                <label htmlFor="moisture">Moisture %</label>
                <input
                  id="moisture"
                  type="number"
                  step="any"
                  min="0"
                  max="100"
                  value={moisture}
                  onChange={(e) => setMoisture(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="plantation">Source plantation</label>
                <input id="plantation" value={sourcePlantation} onChange={(e) => setSourcePlantation(e.target.value)} />
              </div>
            </>
          )}
        </div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save reading"}
          </button>
        </div>
      </form>
    </section>
  );
}

function ProductionRecordForm({ facilityId, onCreated }: { facilityId: string; onCreated: () => void }) {
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [madeTeaKg, setMadeTeaKg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await createProductionRecord({
        facility_id: facilityId,
        period_start: periodStart,
        period_end: periodEnd,
        made_tea_kg: Number(madeTeaKg),
      });
      setMadeTeaKg("");
      setSuccess(true);
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save production record.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <span className="panel-title">Log production</span>
      </div>
      {error && (
        <div style={{ padding: "0 18px" }}>
          <Banner kind="error">{error}</Banner>
        </div>
      )}
      {success && (
        <div style={{ padding: "0 18px" }}>
          <Banner kind="success">Production record saved.</Banner>
        </div>
      )}
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="prod-start">Period start</label>
            <input id="prod-start" type="date" required value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="prod-end">Period end</label>
            <input id="prod-end" type="date" required value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="made-tea">Made tea (kg)</label>
            <input
              id="made-tea"
              type="number"
              step="any"
              min="0"
              required
              value={madeTeaKg}
              onChange={(e) => setMadeTeaKg(e.target.value)}
            />
          </div>
        </div>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save production"}
          </button>
        </div>
      </form>
    </section>
  );
}
