# SolGrid · Tea Energy Intelligence

Backend for the facility energy ledger and business-case engine described in
`SolGrid-Tea-Architecture.md`. First deployment target is NTZDC (Kipchabo,
Gatitu); the schema is deliberately generic so a second C&I customer is a
new `organization` row, not a rewrite.

This build follows the architecture doc's own §9 sequencing: schema + RLS +
Tier-4 web ingestion first, then the benchmark layer, then the scenario
engine. SMS/USSD ingestion, the report_snapshot/Conservation Passport
bridge, and solar-generation ingestion (steps 4–6) are not built yet — see
**What's next** below.

## What's built

- **Schema + migration** (`migrations/versions/0001_initial_schema.py`):
  `organization`, `facility`, `app_user`, `production_record`,
  `energy_reading` (TimescaleDB hypertable), `emission_factor`,
  `energy_content_factor`, `tariff`, `scenario_run`, `report_snapshot`.
- **Row-level security** on every tenant table, `FORCE`d, backed by a
  `current_org_id()` helper that fails closed. A `BEFORE INSERT` trigger
  denormalizes `organization_id` from `facility_id` on every facility-scoped
  table so a client can never forge which tenant a row belongs to.
- **Auth**: JWT (access + refresh), password hashing via werkzeug, a
  `SECURITY DEFINER` `auth_lookup_user()` function for the one legitimate
  cross-tenant read (looking up which org an email belongs to at login).
- **Tier-4 ledger ingestion**, web-form channel: `POST/GET
  /api/v1/ledger/energy-readings` and `/production-records`.
- **Benchmark engine** (`GET /api/v1/benchmark`): cost/kg tea, kWh/kg tea,
  energy mix %, for a facility and period.
- **Scenario engine** (`POST /api/v1/scenarios`): the pure-solar what-if
  calculation from architecture doc §5 — addressable share, savings,
  payback (capex mode) or rate spread (PPA mode), avoided grid emissions.
- Unit tests for the calculation engine and ledger validation (no
  infrastructure needed); integration tests for RLS isolation and the
  benchmark engine (need a live database, auto-skip otherwise).

## Deviations from the architecture doc

The doc is the design intent; a few things in it don't hold up once you try
to actually build and run them. Each is explained where it's implemented,
and repeated here so it's not buried in code comments:

1. **`energy_reading` uses `period_start`/`period_end`, not `ts`.** §2 and
   §3 of the doc contradict each other on this point. §3's reasoning (match
   periods against `production_record`) is the one that matters for the
   calculation engine, so that's what got built.
2. **Every tenant table has a direct `organization_id` column**, not the
   doc's plan of scoping through a `facility_id` subquery. A `tariff` row
   with `facility_id IS NULL` (an org-wide default rate) has no facility to
   subquery through — under the doc's plan that row would be visible to
   every tenant, not just its own.
3. **RLS policies use `current_org_id()`** (`NULLIF(current_setting(...),
   '')::uuid`), not the doc's bare `current_setting('app.org_id')::uuid`.
   Confirmed against a real Postgres instance while building this: the bare
   version throws a hard error instead of denying access, both when
   `app.org_id` was never set and — more subtly — on a pooled connection
   where it was set earlier and later `RESET` (Postgres reverts a custom
   placeholder GUC to `''`, not `NULL`).
4. **`energy_content_factor` is a new table**, not in the doc.
   Cost-per-kg and energy-mix % need to convert litres of diesel and m³ of
   fuelwood into a common energy unit, and the doc's own principle (§0.2:
   versioned, sourced, never hardcoded) says that conversion factor
   shouldn't be a Python constant either.
5. **`SET LOCAL app.org_id = :value` doesn't work** — Postgres rejects a
   bind parameter there (`SET` is parsed, not planned). Every call site uses
   `SELECT set_config('app.org_id', :value, true)` instead, which is a
   normal function call and does accept one. This is not a doc deviation so
   much as something the doc couldn't have caught without running it — worth
   flagging because it would have silently broken tenant isolation.

## Local setup

```bash
cp .env.example .env               # fill in real secrets
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db            # Postgres + TimescaleDB, bootstraps roles
alembic upgrade head

flask --app wsgi.py seed-reference-data
flask --app wsgi.py seed-org --org-name "NTZDC" --admin-email you@example.com \
    --admin-password 'change-me' --facility-name "Kipchabo"

flask --app wsgi.py run
```

Run the full app via Docker instead with `docker compose up --build`.

**Before anything reaches an external report**: `seed-reference-data`
deliberately seeds the Kenya grid `emission_factor` and the fuelwood
`energy_content_factor` as flagged `PLACEHOLDER` rows (see their
`methodology_note`). Replace both with sourced figures before a number
derived from them goes near the Conservation Passport or a brand.

### Tests

```bash
pytest                              # unit tests always run
docker compose up -d db && TEST_DATABASE_URL=postgresql+psycopg://solgrid_app:solgrid_app_password@localhost:5432/solgrid_tea pytest -m db
```

DB-marked tests (`-m db`) skip automatically, not fail, if no database is
reachable.

**Sandbox note**: this was built and tested in an environment without
network access to Docker Hub for the `timescale/timescaledb` image
specifically. Every RLS policy, trigger, function, and grant in the
migration was validated against a live Postgres 16 instance end-to-end
(schema apply, tenant isolation, cross-tenant insert rejection, full HTTP
request cycle from login through ledger writes to a scenario run) — the one
thing *not* directly verified here is the `create_hypertable(...)` call
itself, since that requires the real TimescaleDB extension. Run `alembic
upgrade head` against `docker compose up db` on a machine with normal
network access before treating this as fully verified.

## What's next (architecture doc §9, steps 4–6)

- **SMS/USSD ingestion** via Africa's Talking — same `EnergyReadingCreate`
  schema, new blueprint, `source_channel='sms'`.
- **`report_snapshot` + Conservation Passport bridge** — publish immutable,
  versioned snapshots (internal vs. external payload tiers per §6);
  `superseded_by` is already in the schema for the correction trail.
- **Solar-generation ingestion** once panels are actually contracted at
  either factory — wires into the existing `reading_type='solar_generation'`
  path, real-time via the existing MQTT/Socket.io pipeline per §7.
- **Thermal-efficiency scenario** (fuelwood reduction) — deliberately not
  implemented. The doc cites a 15–30% sector-wide range but no formula; see
  the module docstring in `solgrid_tea/services/calculation_engine.py`.
- A frontend — none exists yet. The API is what a Meridian-design-system
  React app per §7 would call.
