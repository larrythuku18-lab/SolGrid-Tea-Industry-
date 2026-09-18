# SolGrid · Tea Energy Intelligence

Backend for the facility energy ledger and business-case engine described in
`SolGrid-Tea-Architecture.md`. First deployment target is NTZDC (Kipchabo,
Gatitu); the schema is deliberately generic so a second C&I customer is a
new `organization` row, not a rewrite.

This build follows the architecture doc's own §9 sequencing: schema + RLS +
Tier-4 web ingestion first, then the benchmark layer, then the scenario
engine, then the report_snapshot/Conservation Passport bridge. SMS/USSD
ingestion (step 4) is not built yet — see **What's next** below.
Solar-generation monitoring (step 6) *is* built, ahead of the doc's own
sequencing — see deviation #9 below for why, and **Solar monitoring
(presentation data)** for what it actually is.

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
- **Facilities** (`GET/POST /api/v1/facilities`): list and admin-create,
  needed once a second facility (e.g. Gatitu) has to be added past the one
  `seed-org` creates.
- **Tier-4 ledger ingestion**, web-form channel: `POST/GET
  /api/v1/ledger/energy-readings` and `/production-records`.
- **Benchmark engine** (`GET /api/v1/benchmark`): cost/kg tea, kWh/kg tea,
  energy mix %, for a facility and period.
- **Scenario engine** (`POST /api/v1/scenarios`): the pure-solar what-if
  calculation from architecture doc §5 — addressable share, savings,
  payback (capex mode) or rate spread (PPA mode), avoided grid emissions —
  plus an optional **thermal-efficiency add-on** in the same request: an
  operator-stated fuelwood reduction % (their judgment, not a system
  prediction — see the calculation engine's module docstring) produces a
  deterministic cost and emissions delta, reported alongside but never
  folded into the solar savings/payback figures.
- **Extraction assist** (`POST /api/v1/ledger/extract`): photographs a
  KPLC bill, fuelwood delivery note, or production record and proposes
  field values (with per-field confidence, never a value below 0.7) for a
  human to review before submitting through the unchanged ledger
  write endpoints. Never writes to the ledger itself, never stores the
  photo. See **AI features** below for what's actually verified.
- **`report_snapshot` publish + pre-publish checks** (`POST/GET
  /api/v1/reports`): architecture doc §6 — internal (full detail) vs.
  external (curated, no raw KES) payload tiers, gated by three checks: a
  plain-code completeness check (is there ledger data for this period at
  all), an LLM plausibility check (flags a genuine deviation from the
  trailing 6 periods — skips itself, not silently passes, when there's no
  history yet to compare against), and a non-overridable placeholder-data
  check that refuses to publish any figure traced back to a
  `PLACEHOLDER`-flagged `emission_factor` or `energy_content_factor` row.
  The first two are overridable with a logged `override_reason`; the third
  is not.
- **Report correction flow** (`POST /api/v1/reports` with `supersedes`):
  republishing a snapshot for the same facility/period with a `supersedes`
  field pointing at the old snapshot's id runs it through the same three
  checks, then links the old snapshot to the new one via `superseded_by`
  instead of overwriting it — the old figure and who published it stay on
  record, `GET /api/v1/reports/<id>` on the old snapshot now shows
  `superseded_by`. Rejects (422) a `supersedes` id for a different
  facility/period, and (409) one that's already been superseded once.
- **Solar monitoring** (`GET /api/v1/solar/generation`, `GET
  /api/v1/solar/health`, `GET /api/v1/solar/health/history`; migration
  `0002_solar_monitoring.py`) — generation-vs-consumption reconciliation
  (solar generation against total electrical load: grid +
  diesel-kWh-equivalent + solar) and panel/battery health (state of
  charge, state of health, fault status) with plain-code, deterministic
  insights — no model. **Presentation data, not real telemetry** — see
  deviation #9. `flask seed-solar-demo --org-id <id>` backfills daily
  health readings and monthly generation; safe to re-run.
- **Weather-adjusted expected generation** (migration
  `0003_solar_irradiance.py`, `solgrid_tea/services/irradiance_sync.py`)
  — the underperformance check now has two tiers. When cached irradiance
  covers the period, expected kWh = `install_capacity_kw x recorded GHI
  x a standard PVWatts-style performance ratio (0.78)` — real physics,
  not a model, and not an invented capacity factor (0.78 is PVWatts' own
  default derate for temperature/wiring/inverter/soiling losses, the
  same category of constant PVWatts itself uses). Without cached
  irradiance it falls back to the cruder self-relative comparison
  (against the site's own trailing average) that's all this had before —
  see `_generation_insight`'s two tiers in `solar_insights.py`, and the
  test proving the weather-adjusted tier avoids a false positive the
  fallback alone would raise (a genuinely cloudy month misread as a
  fault). `flask sync-solar-irradiance --org-id <id>` fetches and caches
  real daily GHI from Open-Meteo's archive API — **no API key needed**,
  which was the point: this app already needs exactly one
  (`ANTHROPIC_API_KEY`) and this doesn't add a second. Facility
  `latitude`/`longitude` are approximate placeholders seeded by
  `seed-solar-demo` (general Kenyan tea highlands, not a GPS survey of
  either real site) — same disclosure standard as every other
  placeholder in this file.
- **Live feed** (`GET /api/v1/solar/live`, `solgrid_tea/services/solar_live.py`)
  — server-sent events over the same two tables the REST endpoints read.
  Not a simulated tick: `flask seed-solar-live --org-id <id>` appends
  real `solar_health_reading` rows on an interval (default 4s), and the
  stream reports what has actually landed, when it lands — including a
  freshness heartbeat on every poll so a viewer can tell a quiet site
  from a dead connection (`is_stale`, `latest_health_age_s`). SSE over
  `fetch`, not `EventSource` — `EventSource` can't carry the bearer
  token this API authenticates with. Requires the app server to use
  threaded/async workers (see `docker-entrypoint.sh`'s `gthread` note) —
  a sync worker pool would be exhausted by a handful of open dashboard
  tabs, since each holds its connection open between polls.
- **Frontend** (`frontend/`) — React + TypeScript console covering all of
  the above: Overview, Ledger, Benchmark, Scenarios, Solar. Light theme
  with an M-Pesa-inspired green sidebar/primary-action color and white
  cards (Bricolage Grotesque + Hanken Grotesk + JetBrains Mono) — replaced
  the earlier dark plum/amber "Meridian" look at the user's request; see
  `frontend/README.md`. Both Solar charts (`GenerationChart.tsx`,
  `BatteryHistoryChart.tsx`) are hand-rolled SVG components, not a
  charting library — consistent with the frontend's existing
  minimal-dependency approach (no data-fetching library either; see
  `frontend/README.md`). The battery chart merges REST-loaded history
  with whatever the live stream has delivered since page load
  (`useSolarLive`), with exponential-backoff reconnection and a
  20s-silence watchdog independent of the browser noticing the socket
  died.
- **Realistic demo history** (`flask seed-demo-history --org-id <id>`) —
  backfills several months of directionally-realistic energy_reading +
  production_record data for every facility in an org (seasonal
  variation, not flat numbers), calibrated so total energy cost per kg
  made tea lands around the real ~KES 21/kg figure, so
  Overview/Ledger/Benchmark/Scenarios show real trends instead of an
  empty shell. Needs reference-data validity backdated to cover the
  backfilled months — see `seed-reference-data --effective-from`.
  Overview and Benchmark also now default to each facility's latest
  period *on file* rather than the current calendar month, which is
  empty for most of every month in practice (bills arrive after period
  close). Dev/demo tooling only — never point it at a real factory's data.
- Unit tests for the calculation engine, ledger validation, extraction
  guardrails, and the plausibility check's skip logic (no infrastructure
  needed); integration tests for RLS isolation, the benchmark engine, the
  report engine, and solar_insights (need a live database, auto-skip
  otherwise); a live-API extraction test against a synthetic image (needs
  `ANTHROPIC_API_KEY` + credit balance, skips otherwise — see **AI
  features**).

The frontend does not yet have UI for extraction or reports — both are
API-only for now, same status as any other backend-ahead-of-frontend gap
listed below.

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
6. **Thermal-efficiency scenario is a solar-only add-on, not standalone.**
   The doc's §5 table calls fuelwood reduction "modeled separately," which
   could read as its own scenario type with no solar involved. Built the
   other way — `ScenarioInput`'s solar fields stay mandatory, thermal
   fields are optional extras on top — a deliberate, smaller scope decision
   (see the build brief this was built from), not something the doc itself
   settled.
7. **Emissions in `report_snapshot` exclude fuelwood.** Grid electricity and
   diesel get a real emissions figure; fuelwood doesn't, because biogenic
   combustion emissions need a deliberate accounting-standard choice
   (biogenic vs. LULUCF-linked) that nobody has made yet — same reasoning
   `cli.py`'s `seed-reference-data` already uses to skip seeding a fuelwood
   `emission_factor` row. The report engine picks up a fuelwood factor
   automatically once one exists; nothing about this is hardcoded to stay
   this way.
8. **`report_snapshot.methodology_version` versions the report-building
   method, not any individual figure.** Per-figure traceability (which
   emission_factor row produced a number) lives inside the payload itself —
   same pattern the scenario engine already uses (`grid_emission_factor_id`
   alongside `emissions_avoided_grid_tco2`). A single TEXT column can't
   itemize multiple reference rows, so it was never going to serve both
   jobs.
9. **Solar-generation monitoring was built before §9 step 6's own
   precondition** ("only once panels are actually contracted at either
   factory") **is met.** Neither Kipchabo nor Gatitu has contracted panels
   — built anyway, at the user's explicit request, for a presentation.
   Backed entirely by `flask seed-solar-demo` synthetic data (see below),
   not real telemetry. `solar_health_reading` (migration 0002) is also new
   relative to the doc — panel/battery diagnostic state (SoC, SoH, fault
   status) doesn't fit `energy_reading`'s ledger-entry shape (a cost and a
   matched period), so it's a separate table rather than overloading that
   one. Real ESP32 firmware and hardware remain unbuilt; this only adds
   the schema and read path so a real integration has somewhere to land.
   Extended further still, also at explicit request: a real-time feed
   (`GET /api/v1/solar/live`, §7's "Real-time: existing MQTT + Socket.io,
   solar-generation path only") over the *same* synthetic table via
   server-sent events, not the MQTT/Socket.io path §7 names — that path is
   the other Lagriff/Smart-Solar product's device-reading infrastructure
   (see §3's "DeviceReader already has three tiers"), which this repo has
   no access to and no ESP32 traffic to carry yet. SSE was the honest
   choice for what actually exists: real rows landing in Postgres,
   pushed to an open connection, no message broker to stand up for
   readings nothing is currently producing.
   Extended once more, also at explicit request, in a direction the
   architecture doc never anticipated at all: `facility.latitude`/
   `longitude` and a `solar_irradiance_daily` cache table (migration
   0003) feed a weather-adjusted expected-generation check
   (`irradiance_sync.py`, Open-Meteo). This is the one piece of "solar
   optimization" that turned out not to need a model — it's the same
   deterministic-physics category as PVWatts, just implemented directly
   rather than via the `pvlib` library, which was judged unjustified
   weight (numpy/pandas/scipy) for a simplified GHI-based estimate when
   neither factory has verified panel tilt/azimuth to feed a fuller
   model anyway.

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

# Optional, for a populated demo instead of an empty one — see What's built:
flask --app wsgi.py seed-reference-data --effective-from 2025-01-01
flask --app wsgi.py seed-demo-history --org-id <organization_id> --months 8
flask --app wsgi.py seed-solar-demo --org-id <organization_id> --months 8
flask --app wsgi.py sync-solar-irradiance --org-id <organization_id> --days 260

flask --app wsgi.py run

# Optional, in a second terminal — makes the Solar page's live badge
# actually move by appending real rows on an interval:
flask --app wsgi.py seed-solar-live --org-id <organization_id> --interval 4
```

Run the full app via Docker instead with `docker compose up --build`. If
you do, `docker-entrypoint.sh` already runs gunicorn with `gthread`
workers — required for `GET /api/v1/solar/live` (see **What's built**);
running the Flask dev server directly (`flask run`, as above) is
threaded by default and needs no equivalent flag.

**Before anything reaches an external report**: `seed-reference-data`
deliberately seeds the Kenya grid `emission_factor` and the fuelwood
`energy_content_factor` as flagged `PLACEHOLDER` rows (see their
`methodology_note`). Replace both with sourced figures before a number
derived from them goes near the Conservation Passport or a brand — and
note that `report_snapshot` publishing already refuses to do this for you
automatically (see the placeholder-data check above); this note is about
the scenario engine and benchmark endpoints, which don't have that gate.

## AI features

Three features use Claude, per `SolGrid-Tea-AI-Prompts.md`. Set
`ANTHROPIC_API_KEY` in `.env` to use any of them — the SDK reads it
straight from the environment, nothing else to configure.

1. **Extraction assist** (`solgrid_tea/services/extraction.py`) — vision
   call, structured JSON output, confidence-gated (anything under 0.7
   comes back `null`, enforced in code as well as by the prompt).
2. **Pre-publish plausibility check**
   (`solgrid_tea/services/plausibility_check.py`) — text-only, flags a
   period only when it's a genuine outlier against trailing history; skips
   itself entirely (not "checked and clean") when there's no trailing
   history yet.
3. Scenario explainer (`SolGrid-Tea-AI-Prompts.md` §3) — **not built**.
   The prompt and tool contract are written; wiring a chat surface to it
   wasn't in scope for this pass.

**What was and wasn't verified**: this account's `ANTHROPIC_API_KEY` has
zero credit balance, so no live call has actually completed here — every
guardrail (confidence floor, `document_type` override, the plausibility
skip logic, error handling) is verified with the Anthropic client mocked
out, and the full HTTP path (auth → RLS → request validation → the actual
API call) was confirmed to reach the real API and fail *only* on the
credit-balance error, not on anything in this codebase. `tests/
test_extraction_live.py` makes a real call against a synthetically-drawn
image and skips cleanly if it can't complete — a pass there confirms the
plumbing, not extraction accuracy. **No real photographed KPLC bill,
fuelwood note, or production record has been tested against this prompt.**
Per the build brief this was built from: extraction quality is unverified
until that happens, and the 0.7 confidence threshold is a starting guess
that needs calibrating against real misreads once it does.

### Tests

```bash
pytest                              # unit tests always run
docker compose up -d db && TEST_DATABASE_URL=postgresql+psycopg://solgrid_app:solgrid_app_password@localhost:5432/solgrid_tea pytest -m db
```

DB-marked tests (`-m db`) skip automatically, not fail, if no database is
reachable.

### If `docker compose up -d db` hangs or fails pulling the image

This was built and tested in an environment where pulling
`timescale/timescaledb` from Docker Hub reliably hung. Root cause: that
host's Docker Hub DNS returns both IPv4 and IPv6 addresses, but the host
had no real IPv6 route (only link-local) — Docker occasionally picked the
unreachable IPv6 address and hung with `network is unreachable`. If you hit
the same thing:

```bash
echo "precedence ::ffff:0:0/96  100" | sudo tee -a /etc/gai.conf
```

This tells the system resolver to prefer IPv4 over IPv6 system-wide when
both are available. No service restart needed — it applies to the next
`docker pull`. This isn't Docker-specific; it fixes the same class of
problem for any tool on a host with this networking quirk.

If you'd rather not touch system config, or the extension genuinely isn't
available yet: the migration (`migrations/versions/0001_initial_schema.py`)
detects whether `timescaledb` is installed and degrades gracefully —
`energy_reading` is created as an ordinary table instead of a hypertable,
with a printed warning, rather than failing the migration. Everything else
(RLS, triggers, the ledger/benchmark/scenario/facilities API, the frontend)
works identically either way; you only lose TimescaleDB's time-partitioning,
which matters for production data volume, not for local development. Point
`docker-compose.yml`'s `db` service at `postgres:16-alpine` instead of
`timescale/timescaledb:latest-pg16` to use this path.

**What was and wasn't verified here**: every RLS policy, trigger, function,
and grant in the migration was validated against a live Postgres 16
instance end-to-end (schema apply, tenant isolation, cross-tenant insert
rejection, full HTTP request cycle from login through ledger writes to a
scenario run), including the graceful-degradation path above via the real
`alembic upgrade head` command. The frontend was verified the same way —
backend + this same plain-Postgres stand-in + the Vite dev server, driven
with headless Chromium (Playwright) through login and all four pages,
screenshotted, zero browser console errors. What's *not* verified here:
real hypertable partitioning behavior, since that needs the actual
TimescaleDB extension, which this environment couldn't pull.

## What's next (architecture doc §9 step 4, plus gaps of its own)

- **SMS/USSD ingestion** via Africa's Talking — same `EnergyReadingCreate`
  schema, new blueprint, `source_channel='sms'`.
- **Real ESP32 solar telemetry.** Solar monitoring itself is built, live
  feed included (see deviation #9 and **What's built**), but every
  reading behind it is synthetic (`seed-solar-demo` / `seed-solar-live`,
  `source_channel='seed'`). What's missing is only the producer: ESP32
  firmware writing `solar_generation` energy_reading rows and
  `solar_health_reading` rows with `source_channel='esp32'` (the schema
  already has the slot, and `GET /api/v1/solar/live` already streams
  whatever lands in that table — a real device pushing rows needs no
  changes on the read side at all). §7's MQTT + Socket.io path is the
  other Lagriff/Smart-Solar product's ingestion infrastructure; whether
  this module reuses it or keeps its own SSE feed once real hardware
  exists is an open question, not a foregone one.
- **Scenario explainer** (`SolGrid-Tea-AI-Prompts.md` §3) — prompt and
  tool contract written, not wired to any chat surface.
- Frontend gaps: no facility-management beyond add (no edit/deactivate
  UI), no extraction or report/passport UI (both are API-only — see **AI
  features**), no thermal-efficiency fields in the scenario form, no
  role-management UI for inviting additional `app_user` accounts (there's
  no invite endpoint yet — new users currently need direct DB access or a
  future admin endpoint).
