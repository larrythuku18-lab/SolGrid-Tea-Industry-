# SolGrid · Tea Energy Intelligence — Console

React + TypeScript frontend for the backend in the repo root. Light
theme, M-Pesa-inspired: a green (`#059450`) sidebar and primary actions
on a white/pale-green canvas, amber (`#EA9A2E`) reserved for
solar-specific data so it doesn't compete with the brand green
(Bricolage Grotesque + Hanken Grotesk + JetBrains Mono). Replaced the
earlier dark plum/amber "Meridian" theme (ported from the Lagriff
console reference) at the user's explicit request — see `src/styles/theme.css`.

## Pages

- **Overview** — facility picker, tiles for the facility's latest period
  *on file* (not the current calendar month — see below), energy mix
  bar, recent ledger entries.
- **Ledger** — Tier-4 web-form ingestion: log energy readings and
  production records; admins can add a facility inline.
- **Benchmark** — run the cost/kg + energy-mix engine for any facility and
  period; defaults to the facility's latest period on file, same reasoning
  as Overview.
- **Scenarios** — the pure-solar what-if builder (capex or PPA), full
  result set including the methodology note for the emission factor used.
  Baseline annual kWh fields are pre-filled from the facility's own ledger
  history (extrapolated to a full year if less than one is on file) —
  editable, not authoritative; see `useLatestPeriod` / the effect in
  `ScenarioPage.tsx`.

Overview and Benchmark default to the facility's most recent
production-record period rather than the current calendar month — a
factory's bills for the current month usually aren't in yet, so "this
month" was empty for most of every month. See `useLatestPeriod`.

## Setup

```bash
cp .env.example .env   # points at the Flask API, default http://localhost:5000
npm install
npm run dev
```

Requires the backend running (see the root README) with at least one
organization/facility seeded via `flask seed-org`.

## Notes

- Auth: JWT stored in `localStorage`, silent refresh on a 401 (see
  `src/api/client.ts`). Acceptable for an internal ops console; revisit if
  this ever needs to resist XSS-based token theft more strongly (httpOnly
  cookies + CSRF token would be the next step).
- No data-fetching library (React Query etc.) — pages fetch in a plain
  `useEffect`. Fine at this size; worth introducing if the number of
  screens grows enough that request deduping/caching starts to matter.
- `public/apple-touch-icon.png` is the brand mark used as both favicon
  and the in-app sidebar/login logo (`.brand-mark`) — reused from the
  Lagriff/Smart-Solar project's icon set at the user's request.
- `npm run build` type-checks (`tsc -b`) before bundling — a type error
  fails the build, not just the lint step.
