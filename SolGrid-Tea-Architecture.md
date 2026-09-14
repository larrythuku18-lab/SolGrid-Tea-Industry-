# SolGrid · Tea Energy Intelligence — Architecture

Scope: NTZDC (Kipchabo, Gatitu) is the first deployment. The system is not built
tea-specific at the schema level — it's built as a general facility energy
ledger and business-case engine, aimed first at tea, sellable to the next
C&I customer without a rewrite.

---

## 0. Design principles

These drive every choice below.

1. **Reuse the proven parts of SolGrid, don't fork it.** DeviceReader, Postgres,
   JWT auth, the Meridian design system — all carry over. Don't rebuild what
   already works.
2. **Anything used in an external report must be deterministic, not ML.**
   Payback period, cost savings, emissions — these are formulas, not
   predictions. A brand or auditor reading the Conservation Passport needs to
   be able to trace every number back to an input and a method. A model that
   can't explain itself doesn't belong in a business case.
3. **Match infrastructure to data frequency.** Fuelwood deliveries happen a
   few times a week. Electricity bills happen monthly. Nothing here needs
   real-time streaming except the one thing that's genuinely a stream: solar
   inverter telemetry, once panels exist.
4. **Everything published externally is versioned and immutable.** Internal
   data can be corrected. A report a brand has already seen cannot silently
   change underneath them.
5. **Multi-tenant from day one, even with one tenant today.** Retrofitting
   tenant isolation after a schema is live is expensive. Adding one column
   and one RLS policy now is not.

---

## 1. System boundary

This is a **standalone service** with its own database, not code embedded
inside ForestOS. ForestOS calls it over a versioned API; it does not reach
into ForestOS's database or vice versa.

This isn't just clean design — it's what makes the Background-IP / licensed-
not-assigned structure real. A module can be "part of ForestOS" commercially
without being part of its codebase. Keep the seam sharp.

```
                     ┌───────────────────────────────┐
                     │            ForestOS             │
                     │  (Conservation Passport, NTZDC   │
                     │   operational data, other modules)│
                     └────────────────┬────────────────┘
                                       │  versioned REST + webhook
                                       │  (read-only, published snapshots)
                     ┌────────────────▼────────────────┐
                     │   SolGrid · Tea Energy Intelligence │
                     │                                     │
                     │  ┌───────────┐     ┌─────────────┐ │
                     │  │ Ingestion  │     │  Reporting / │ │
                     │  │  layer     │     │  Export       │ │
                     │  └─────┬──────┘     └──────▲──────┘ │
                     │        │                    │        │
                     │  ┌─────▼────────────────────┴─────┐ │
                     │  │   Domain DB (Postgres+Timescale) │ │
                     │  └─────┬────────────────────────┘ │
                     │        │                             │
                     │  ┌─────▼──────┐                      │
                     │  │ Calculation │                      │
                     │  │   Engine    │                      │
                     │  │ (Benchmark +│                      │
                     │  │  Scenario)  │                      │
                     │  └────────────┘                      │
                     └───────────────────────────────────────┘
                        ▲                          ▲
                        │                          │
              ┌─────────┴────────┐       ┌─────────┴─────────┐
              │  Device telemetry │       │  Manual / SMS entry │
              │  (inverters, via  │       │  (bills, fuelwood,  │
              │  existing tiers)  │       │   production)       │
              └───────────────────┘       └────────────────────┘
```

---

## 2. Data model

Core entities. Names are generic on purpose — tea is the first customer, not
a permanent constraint baked into the schema.

```sql
-- tenancy + facility
CREATE TABLE organization (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    sector TEXT NOT NULL DEFAULT 'tea'          -- descriptive, not structural
);

CREATE TABLE facility (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization(id),
    name TEXT NOT NULL,                          -- 'Kipchabo', 'Gatitu'
    county TEXT,
    install_capacity_kw NUMERIC                  -- solar; null until installed
);

-- output
CREATE TABLE production_record (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID NOT NULL REFERENCES facility(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    made_tea_kg NUMERIC NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual'
);

-- the ledger: one typed, time-series table for every energy input
CREATE TABLE energy_reading (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID NOT NULL REFERENCES facility(id),
    reading_type TEXT NOT NULL CHECK (reading_type IN
        ('grid_electricity','diesel','fuelwood','solar_generation')),
    ts TIMESTAMPTZ NOT NULL,
    quantity NUMERIC NOT NULL,                   -- kWh, litres, or m3
    unit TEXT NOT NULL,
    cost_kes NUMERIC,                             -- null for solar_generation
    moisture_pct NUMERIC,                         -- fuelwood only
    source_plantation TEXT,                       -- fuelwood only — custody trail
    source_channel TEXT NOT NULL CHECK (source_channel IN
        ('esp32','modbus','oem_api','manual','sms')),
    entered_by TEXT
);
SELECT create_hypertable('energy_reading', 'ts');

-- reference data — versioned, never hardcoded in application code
CREATE TABLE emission_factor (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fuel_type TEXT NOT NULL,
    kg_co2_per_unit NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    effective_from DATE NOT NULL,
    methodology_note TEXT NOT NULL                -- source, required, no exceptions
);

CREATE TABLE tariff (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID REFERENCES facility(id),     -- null = org default
    fuel_type TEXT NOT NULL,
    price_kes_per_unit NUMERIC NOT NULL,
    effective_from DATE NOT NULL
);

-- saved what-if runs
CREATE TABLE scenario_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID NOT NULL REFERENCES facility(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assumptions JSONB NOT NULL,
    results JSONB NOT NULL,                       -- itemized, see §5
    created_by TEXT
);

-- published, immutable
CREATE TABLE report_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    facility_id UUID NOT NULL REFERENCES facility(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL,
    methodology_version TEXT NOT NULL,
    superseded_by UUID REFERENCES report_snapshot(id)   -- correction trail
);
```

`energy_reading` is the whole ledger in one typed table rather than four
separate ones. One hypertable, one place to query "everything at Kipchabo in
March," and `reading_type` keeps the CHECK constraint doing the work a
separate-tables design would push into application code.

---

## 3. Ingestion layer

DeviceReader already has three tiers — ESP32, Modbus, OEM API (Growatt, Deye,
Huawei). Add a fourth:

**Tier 4 — Ledger.** Manual and CSV entry for grid bills, fuelwood
deliveries, and production records. Two capture channels:

- **Web form**, reusing the existing console's design system, for anyone
  with a reliable connection.
- **SMS/USSD via Africa's Talking** (already integrated) for factory-level
  staff logging a fuelwood delivery from a basic phone. This matters more
  than it looks — Kipchabo and Gatitu are rural, and the data that actually
  needs field capture (wood delivered today, moisture, source zone) is
  exactly the data least likely to have someone at a laptop when it happens.

One data-quality rule worth encoding, not just documenting: **match periods
on entry.** Wood burned this week dried leaf picked this week; a bill covers
last month. The ingestion layer should require a `period_start`/`period_end`
on every record rather than a single timestamp, so the calculation engine
never has to guess what production a cost belongs to.

---

## 4. Storage

**PostgreSQL + TimescaleDB extension.** Not a separate time-series database.
`energy_reading` is a hypertable; `production_record`, `tariff`,
`emission_factor` stay ordinary relational tables in the same instance. One
database to operate, one to back up, one SQL dialect — for a system meant to
run for years with minimal attention, that's worth more than the marginal
performance a dedicated time-series store would add at this scale.

**Row-level security for tenant isolation**, enforced at the database, not
just in application code:

```sql
ALTER TABLE energy_reading ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON energy_reading
    USING (facility_id IN (
        SELECT id FROM facility
        WHERE organization_id = current_setting('app.org_id')::uuid
    ));
```

One customer today, but a cross-tenant data leak is the kind of failure that
ends a B2B sustainability-reporting product's credibility in one incident.
Cheap to build in now, expensive to bolt on after a second customer signs.

---

## 5. Calculation engine

Plain Python. Pydantic models for every scenario, so bad units or missing
assumptions fail at the boundary, not three formulas deep. This is the layer
that answers the seven modeling questions directly:

```python
class ScenarioInput(BaseModel):
    facility_id: UUID
    financing_mode: Literal["ppa", "capex"]
    target_solar_kw: float
    grid_tariff_kes_per_kwh: float
    ppa_rate_kes_per_kwh: float | None = None      # required if ppa
    capex_kes: float | None = None                  # required if capex
    daytime_coincidence_factor: float = 0.50         # KTDA sector default;
                                                       # override once metered

class ScenarioResult(BaseModel):
    addressable_electrical_share_pct: float
    addressable_of_total_energy_pct: float           # always << the above —
                                                        # solar caps at the
                                                        # electrical share
    annual_savings_kes: float
    payback_years: float | None                       # null under ppa —
                                                        # "payback" isn't the
                                                        # right frame there
    emissions_avoided_grid_tco2: float
    emissions_avoided_fuelwood_tco2: float             # 0 unless a thermal-
                                                        # efficiency scenario
                                                        # is run separately
    fuelwood_reduction_m3: float                       # 0 for a pure-solar
                                                        # scenario — solar
                                                        # doesn't touch wood
```

That last field isn't decoration — it's the earlier correction enforced by
the type itself. A pure-solar scenario literally cannot report a nonzero
fuelwood reduction; the two are only ever populated together when someone
explicitly runs a thermal-efficiency scenario alongside the solar one.

**Mapping the seven questions:**

| Question | Where it's answered |
|---|---|
| Cost per kg of tea | `(electricity_cost + fuelwood_cost) / made_tea_kg` for a matched period, from `energy_reading` × `production_record` |
| % of energy movable to solar | `addressable_electrical_share_pct` — capped by electrical's real share of total energy (~12–15% sector-wide), not total demand |
| Annual savings | `addressable_kwh × (grid_tariff − effective_solar_cost)`, where effective cost is the PPA rate or blended capex cost depending on `financing_mode` |
| Payback period | Capex mode only: `capex_kes / annual_savings_kes`. PPA mode reports a tariff discount instead, not a payback figure |
| Fuelwood reduction | Not from a solar scenario. Modeled separately as a thermal-efficiency scenario (better dryers, briquette blending, operational practice — the sector has documented 15–30% thermal reductions from practice changes alone) |
| Carbon reduction | Two line items, never one blended number: grid-displacement emissions (small — Kenya's grid is mostly geothermal/hydro) and fuelwood-efficiency emissions (the bigger lever, only if that scenario is run) |
| Feed the Conservation Passport | `report_snapshot` — see §6 |

---

## 6. Reporting / Conservation Passport bridge

A `report_snapshot` per facility per period, published once and frozen.
ForestOS pulls or is pushed the payload; it never queries live operational
tables. If a number is later corrected, a new snapshot supersedes the old
one via `superseded_by` — the trail stays intact rather than the old figure
quietly vanishing.

Two visibility tiers on the payload:

- **Internal** — full cost figures, factory-level detail, raw ledger access.
  NTZDC and Ganmbare Devs only.
- **External (Passport)** — a curated subset: energy mix %, emissions
  figures with `methodology_version` attached, verification status. No raw
  KES cost data goes to a brand or offtaker by default.

`methodology_version` on every published figure is what keeps this
audit-ready without overclaiming. It's metered data with a stated method —
not a carbon credit, and the schema doesn't pretend otherwise.

---

## 7. Stack summary

| Layer | Choice | Why |
|---|---|---|
| Backend | Flask, Blueprints per module | Already proven, already debugged, already known — no reason to pay a framework-migration cost for this |
| Validation | Pydantic (plain, not framework-bound) | Catches bad scenario inputs at the boundary; makes the engine's contract explicit |
| Database | Postgres + TimescaleDB | One instance, hypertables for the ledger, ordinary tables for everything else |
| Scheduling | APScheduler (in-process) | Nightly benchmark recompute, monthly snapshot — doesn't justify Celery + Redis at this volume |
| Real-time | Existing MQTT + Socket.io, solar-generation path only | Ledger data isn't a stream; don't build streaming infra for a weekly delivery record |
| Frontend | React, Meridian design system (Bricolage Grotesque / Hanken Grotesk / JetBrains Mono, plum + amber) | Same visual language as the rest of SolGrid — no new brand surface for one module |
| Auth | JWT + Postgres RLS | Tenant isolation enforced at the database, not trusted to application code alone |
| Hosting | Single managed Postgres, single app service | No microservices, no Kubernetes — a solo founder maintaining this for years needs boring infrastructure, not impressive infrastructure |

---

## 8. Explicitly out of scope for v1

Naming what this deliberately doesn't do matters as much as the architecture
itself:

- **PAYG billing / remote lockout.** No financed asset exists at NTZDC yet.
  Nothing for M-Pesa STK Push or a lockout to attach to. Reserved capability
  in the wider SolGrid platform, not built into this module.
- **ML-based savings or payback prediction.** Deterministic only, for the
  reasons in §0.2.
- **Real-time streaming for ledger data.** Covered by §0.3 — the data
  doesn't move fast enough to justify it.
- **Cross-tenant analytics or benchmarking against other customers.** Not
  until there's a second tenant, and even then, only with consent.

---

## 9. Build sequencing

1. Schema + RLS + Tier-4 ledger ingestion (web form only).
2. Benchmark layer — cost/kg, MJ/kg, by facility and period. This alone is
   sellable and demoable before any modeling exists.
3. Scenario engine + the seven-question mapping in §5.
4. SMS/USSD capture channel.
5. `report_snapshot` + Conservation Passport API contract.
6. Solar-generation ingestion, only once panels are actually contracted at
   either factory.

Steps 1–3 need 24 months of real KPLC bills, fuelwood records, and
production data to calibrate against — the test already put to NTZDC. No
step here depends on solar existing; only step 6 does.

---

## 10. Why this holds up long-term

Boring core (Flask, Postgres) means fewer things to maintain. Versioned
reference tables mean the methodology can be challenged and defended without
touching code. A deterministic engine means the output survives scrutiny
from someone who isn't you. A generic schema under a tea-flavored surface
means the next C&I customer is a new `organization` row, not a rewrite.
Tenant isolation from day one means that customer doesn't require a
migration to onboard safely. None of this is exotic — that's the point.
