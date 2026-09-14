# SolGrid · Tea Energy Intelligence — Console

React + TypeScript frontend for the backend in the repo root. Visual
language is the real Meridian design system (dark plum `#14101F` /
solar-amber `#FDB44B` / volt-teal `#37D9C5`, Bricolage Grotesque + Hanken
Grotesk + JetBrains Mono) ported from the Lagriff console reference, per
the architecture doc's "no new brand surface for one module."

## Pages

- **Overview** — facility picker, this-month tiles (tea produced, energy
  cost, cost/kg, kWh/kg), energy mix bar, recent ledger entries.
- **Ledger** — Tier-4 web-form ingestion: log energy readings and
  production records; admins can add a facility inline.
- **Benchmark** — run the cost/kg + energy-mix engine for any facility and
  period.
- **Scenarios** — the pure-solar what-if builder (capex or PPA), full
  result set including the methodology note for the emission factor used.

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
- `npm run build` type-checks (`tsc -b`) before bundling — a type error
  fails the build, not just the lint step.
