import calendar
import random
import uuid
from datetime import date, datetime, timezone

import click
from sqlalchemy import select, text

from solgrid_tea.extensions import db
from solgrid_tea.models import (
    AppUser,
    EmissionFactor,
    EnergyContentFactor,
    EnergyReading,
    Facility,
    Organization,
    ProductionRecord,
    SolarHealthReading,
)


def register_cli(app):
    @app.cli.command("seed-org")
    @click.option("--org-name", required=True)
    @click.option("--admin-email", required=True)
    @click.option("--admin-password", required=True)
    @click.option("--facility-name", required=True)
    def seed_org(org_name, admin_email, admin_password, facility_name):
        """Bootstrap a brand-new tenant: organization + first admin + one facility.

        organization is RLS-protected like every tenant table, which is a
        chicken-and-egg problem for the very first insert. Fix: generate the
        id client-side and set app.org_id to match before inserting, so the
        row satisfies its own RLS policy.
        """
        org_id = uuid.uuid4()
        # See solgrid_tea.security.tenant_context: SET LOCAL rejects bind
        # parameters, set_config() doesn't.
        db.session.execute(
            text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
        )

        org = Organization(id=org_id, name=org_name)
        db.session.add(org)
        db.session.flush()

        facility = Facility(organization_id=org.id, name=facility_name)
        db.session.add(facility)

        admin = AppUser(organization_id=org.id, email=admin_email.lower(), role="admin")
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.flush()

        # Read ids out before commit: commit() expires every ORM attribute,
        # and the next access re-queries — by then app.org_id (set only for
        # this transaction, via set_config's is_local=true) is gone, so RLS
        # blocks that re-query and raises ObjectDeletedError instead of
        # just returning the value.
        org_id, facility_id, admin_id = org.id, facility.id, admin.id
        db.session.commit()
        click.echo(f"organization_id={org_id} facility_id={facility_id} admin_user_id={admin_id}")

    @app.cli.command("seed-reference-data")
    @click.option(
        "--effective-from",
        "effective_from",
        default=None,
        help=(
            "Date these factors are valid from (YYYY-MM-DD). Defaults to today. "
            "Pass an earlier date to backfill validity for historical ledger "
            "data — latest_emission_factor()/latest_energy_content_factor() "
            "pick the newest row with effective_from <= the period in "
            "question, so an earlier row here doesn't touch or weaken "
            "whatever's already on file for later dates."
        ),
    )
    def seed_reference_data(effective_from):
        """Seed emission_factor / energy_content_factor with starting values.

        These are global reference tables (no RLS, no tenant), but they are
        NOT all equally trustworthy. Physical constants (diesel calorific
        value, standard diesel combustion emissions) are safe defaults.
        Region-specific figures — Kenya's grid emission factor, fuelwood
        calorific value for NTZDC's actual species/moisture — are seeded as
        explicitly flagged placeholders. Do not let a report reach a brand
        or auditor citing a PLACEHOLDER row; replace it with a sourced
        figure first.
        """
        today = date.fromisoformat(effective_from) if effective_from else date.today()

        db.session.add_all(
            [
                EnergyContentFactor(
                    fuel_type="grid_electricity",
                    kwh_per_unit=1.0,
                    unit="kWh",
                    effective_from=today,
                    methodology_note="Identity conversion — grid readings are already in kWh.",
                ),
                EnergyContentFactor(
                    fuel_type="diesel",
                    kwh_per_unit=10.72,
                    unit="litre",
                    effective_from=today,
                    methodology_note=(
                        "38.6 MJ/L standard diesel gross calorific value / 3.6 = 10.72 kWh/L. "
                        "Widely-published default, not region-specific."
                    ),
                ),
                EnergyContentFactor(
                    fuel_type="fuelwood",
                    kwh_per_unit=1500.0,
                    unit="m3",
                    effective_from=today,
                    methodology_note=(
                        "PLACEHOLDER — rough mid-estimate (~600 kg/m3 * 2.5 kWh/kg). Fuelwood "
                        "energy content varies heavily by species and moisture_pct. Replace with "
                        "a figure sourced to NTZDC's actual wood species before this feeds any "
                        "benchmark used outside internal estimation."
                    ),
                ),
                EmissionFactor(
                    fuel_type="grid_electricity",
                    kg_co2_per_unit=0.11,
                    unit="kWh",
                    effective_from=today,
                    methodology_note=(
                        "PLACEHOLDER pending the current published Kenya national grid emission "
                        "factor. Replace before any figure derived from this reaches the "
                        "Conservation Passport or another external-facing report."
                    ),
                ),
                EmissionFactor(
                    fuel_type="diesel",
                    kg_co2_per_unit=2.68,
                    unit="litre",
                    effective_from=today,
                    methodology_note=(
                        "Standard diesel combustion default (~2.68 kgCO2/L), consistent with "
                        "common IPCC-derived defaults. Not region-specific."
                    ),
                ),
            ]
        )
        db.session.commit()
        click.echo("reference data seeded — grid_electricity emission factor is a PLACEHOLDER")

    # Rough per-facility sizing so demo history looks like two different
    # real factories rather than the same numbers twice. Kenyan tea
    # production is seasonal — peak around Mar-May and Oct-Dec, lower
    # Jan-Feb and Jul-Aug — so month-to-month variation isn't just noise.
    # Intensity factors calibrated so total energy cost / made_tea_kg lands
    # around KES 21/kg (confirmed real figure) rather than the ~15 an
    # earlier pass produced — scaled up ~1.4x from the original guess,
    # keeping the same energy-mix shape (fuelwood-dominated).
    _DEMO_FACILITY_PROFILES = {
        "Kipchabo": {
            "base_tea_kg": 450_000, "kwh_per_kg": 0.50,
            "diesel_per_1000kg": 3.6, "fuelwood_m3_per_1000kg": 3.4,
        },
        "Gatitu": {
            "base_tea_kg": 220_000, "kwh_per_kg": 0.48,
            "diesel_per_1000kg": 3.1, "fuelwood_m3_per_1000kg": 3.2,
        },
        "_default": {
            "base_tea_kg": 300_000, "kwh_per_kg": 0.49,
            "diesel_per_1000kg": 3.4, "fuelwood_m3_per_1000kg": 3.3,
        },
    }
    _DEMO_SEASONAL_MULTIPLIER = {
        1: 0.88, 2: 0.85, 3: 1.05, 4: 1.15, 5: 1.12, 6: 1.00,
        7: 0.92, 8: 0.90, 9: 0.95, 10: 1.08, 11: 1.10, 12: 1.02,
    }

    @app.cli.command("seed-demo-history")
    @click.option("--org-id", "org_id", required=True, type=click.UUID)
    @click.option("--months", default=8, show_default=True, help="Completed calendar months to backfill.")
    @click.option("--seed", "rand_seed", default=None, type=int, help="Fix the RNG for reproducible output.")
    def seed_demo_history(org_id, months, rand_seed):
        """Backfill realistic energy_reading + production_record history for
        every facility in an org, so dashboards show real trends instead of
        an empty shell.

        Safe to re-run: replaces whatever energy_reading/production_record
        rows already exist for the specific months it (re)generates, rather
        than piling up duplicates, so recalibrating the profile numbers and
        re-running just works.

        Dev/demo tool only — a real factory's history should come from
        actual ledger entries (or extraction assist / SMS ingestion once
        built), never from this; it will delete real entries for any month
        it's pointed at. Figures are directionally realistic for a mid-size
        Kenyan KTDA-affiliated tea factory, not audited data. Requires
        reference data effective before the earliest backfilled month — see
        seed-reference-data --effective-from.
        """
        rng = random.Random(rand_seed)
        org_id = uuid.UUID(str(org_id))
        db.session.execute(
            text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
        )
        facilities = db.session.scalars(
            select(Facility).where(Facility.organization_id == org_id)
        ).all()
        if not facilities:
            click.echo(f"no facilities found for org {org_id}")
            return

        today = date.today()
        # Completed calendar months only, most recent first: (year, month)
        # for the month before the current one, going back `months` steps.
        periods = []
        y, m = today.year, today.month
        for _ in range(months):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
            periods.append((y, m))

        rows_inserted = 0
        for facility in facilities:
            profile = _DEMO_FACILITY_PROFILES.get(facility.name, _DEMO_FACILITY_PROFILES["_default"])
            for year, month in periods:
                period_start = date(year, month, 1)
                period_end = date(year, month, calendar.monthrange(year, month)[1])
                db.session.execute(
                    text(
                        "DELETE FROM energy_reading "
                        "WHERE facility_id = :f AND period_start = :ps AND period_end = :pe"
                    ),
                    {"f": str(facility.id), "ps": period_start, "pe": period_end},
                )
                db.session.execute(
                    text(
                        "DELETE FROM production_record "
                        "WHERE facility_id = :f AND period_start = :ps AND period_end = :pe"
                    ),
                    {"f": str(facility.id), "ps": period_start, "pe": period_end},
                )
                seasonal = _DEMO_SEASONAL_MULTIPLIER[month]

                made_tea_kg = round(profile["base_tea_kg"] * seasonal * rng.uniform(0.90, 1.10))
                grid_kwh = round(made_tea_kg * profile["kwh_per_kg"] * rng.uniform(0.95, 1.05))
                diesel_litres = round(
                    (made_tea_kg / 1000) * profile["diesel_per_1000kg"] * rng.uniform(0.70, 1.40)
                )
                fuelwood_m3 = round(
                    (made_tea_kg / 1000) * profile["fuelwood_m3_per_1000kg"] * rng.uniform(0.92, 1.08)
                )

                grid_tariff_kes = rng.uniform(14.3, 15.6)
                diesel_price_kes = rng.uniform(178, 196)
                fuelwood_price_kes = rng.uniform(3800, 4300)

                db.session.add(
                    ProductionRecord(
                        facility_id=facility.id,
                        period_start=period_start,
                        period_end=period_end,
                        made_tea_kg=made_tea_kg,
                        source="manual",
                    )
                )
                db.session.add(
                    EnergyReading(
                        facility_id=facility.id,
                        reading_type="grid_electricity",
                        period_start=period_start,
                        period_end=period_end,
                        quantity=grid_kwh,
                        unit="kWh",
                        cost_kes=round(grid_kwh * grid_tariff_kes),
                        source_channel="manual",
                    )
                )
                db.session.add(
                    EnergyReading(
                        facility_id=facility.id,
                        reading_type="diesel",
                        period_start=period_start,
                        period_end=period_end,
                        quantity=diesel_litres,
                        unit="litre",
                        cost_kes=round(diesel_litres * diesel_price_kes),
                        source_channel="manual",
                    )
                )
                db.session.add(
                    EnergyReading(
                        facility_id=facility.id,
                        reading_type="fuelwood",
                        period_start=period_start,
                        period_end=period_end,
                        quantity=fuelwood_m3,
                        unit="m3",
                        cost_kes=round(fuelwood_m3 * fuelwood_price_kes),
                        source_channel="manual",
                    )
                )
                rows_inserted += 4

        db.session.commit()
        click.echo(f"seeded {rows_inserted} ledger rows across {len(facilities)} facilit(y/ies)")

    # Hypothetical install sizing + a monthly solar capacity-factor assumption
    # used only to *generate* this synthetic demo data — a concrete number an
    # operator would need to supply for a real site (see scenario engine's
    # solar_capacity_factor field, "no safe platform default"). Not used
    # anywhere in solar_insights.py's read path, which deliberately avoids
    # assuming a capacity factor at query time.
    _SOLAR_DEMO_PROFILES = {
        "Kipchabo": {
            "install_capacity_kw": 150, "capacity_factor": 0.205,
            "start_soh_pct": 98.0, "soh_monthly_drop_pct": 0.5, "trouble": False,
        },
        "Gatitu": {
            "install_capacity_kw": 80, "capacity_factor": 0.195,
            "start_soh_pct": 98.0, "soh_monthly_drop_pct": 1.1, "trouble": True,
        },
        "_default": {
            "install_capacity_kw": 60, "capacity_factor": 0.20,
            "start_soh_pct": 97.0, "soh_monthly_drop_pct": 0.6, "trouble": False,
        },
    }
    # Kenya's solar irradiance is fairly consistent year-round near the
    # equator, but cloud cover during the long/short rains (Mar-May,
    # Oct-Nov) knocks generation down a bit — a milder effect than the tea
    # seasonality in _DEMO_SEASONAL_MULTIPLIER, and a different shape.
    _SOLAR_SEASONAL_MULTIPLIER = {
        1: 1.05, 2: 1.08, 3: 0.92, 4: 0.85, 5: 0.90, 6: 1.00,
        7: 0.95, 8: 1.00, 9: 1.02, 10: 0.90, 11: 0.87, 12: 1.00,
    }

    @app.cli.command("seed-solar-demo")
    @click.option("--org-id", "org_id", required=True, type=click.UUID)
    @click.option("--months", default=8, show_default=True, help="Completed calendar months to backfill.")
    @click.option("--seed", "rand_seed", default=None, type=int, help="Fix the RNG for reproducible output.")
    def seed_solar_demo(org_id, months, rand_seed):
        """Backfill solar_generation energy_reading rows and
        solar_health_reading (panel/battery) rows for every facility in an
        org, and set facility.install_capacity_kw if it isn't already set.

        Presentation tool only — see migrations/0002's docstring. Neither
        Kipchabo nor Gatitu has contracted panels yet; this data does not
        represent anything installed in reality. Real generation should come
        from ESP32 telemetry once that firmware and hardware exist. Safe to
        re-run: replaces existing solar_generation/solar_health_reading rows
        for the months it (re)generates.
        """
        rng = random.Random(rand_seed)
        org_id = uuid.UUID(str(org_id))
        db.session.execute(
            text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
        )
        facilities = db.session.scalars(
            select(Facility).where(Facility.organization_id == org_id)
        ).all()
        if not facilities:
            click.echo(f"no facilities found for org {org_id}")
            return

        today = date.today()
        periods = []
        y, m = today.year, today.month
        for _ in range(months):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
            periods.append((y, m))
        periods.reverse()  # oldest first, so SoH degrades forward in time

        rows_inserted = 0
        for facility in facilities:
            profile = _SOLAR_DEMO_PROFILES.get(facility.name, _SOLAR_DEMO_PROFILES["_default"])
            if facility.install_capacity_kw is None:
                facility.install_capacity_kw = profile["install_capacity_kw"]

            trouble_index = len(periods) - 1 if profile["trouble"] else None
            soh = profile["start_soh_pct"]

            for i, (year, month) in enumerate(periods):
                period_start = date(year, month, 1)
                period_end = date(year, month, calendar.monthrange(year, month)[1])

                db.session.execute(
                    text(
                        "DELETE FROM energy_reading WHERE facility_id = :f "
                        "AND period_start = :ps AND period_end = :pe "
                        "AND reading_type = 'solar_generation'"
                    ),
                    {"f": str(facility.id), "ps": period_start, "pe": period_end},
                )
                db.session.execute(
                    text(
                        "DELETE FROM solar_health_reading WHERE facility_id = :f "
                        "AND ts >= :ps AND ts <= :pe"
                    ),
                    {"f": str(facility.id), "ps": period_start, "pe": period_end},
                )

                days_in_month = (period_end - period_start).days + 1
                seasonal = _SOLAR_SEASONAL_MULTIPLIER[month]
                generation_kwh = round(
                    profile["install_capacity_kw"]
                    * profile["capacity_factor"]
                    * 24
                    * days_in_month
                    * seasonal
                    * rng.uniform(0.92, 1.08)
                )

                is_trouble_month = trouble_index is not None and i == trouble_index
                panel_status = "normal"
                battery_status = "normal"
                if is_trouble_month:
                    generation_kwh = round(generation_kwh * rng.uniform(0.55, 0.68))
                    panel_status = "underperforming"

                db.session.add(
                    EnergyReading(
                        facility_id=facility.id,
                        reading_type="solar_generation",
                        period_start=period_start,
                        period_end=period_end,
                        quantity=generation_kwh,
                        unit="kWh",
                        cost_kes=None,
                        source_channel="manual",
                    )
                )

                soh = max(0.0, soh - profile["soh_monthly_drop_pct"] * rng.uniform(0.7, 1.3))
                soc = rng.uniform(30, 45) if is_trouble_month else rng.uniform(50, 82)
                panel_temp_c = rng.uniform(34, 48)
                reading_ts = datetime(year, month, period_end.day, 12, 0, tzinfo=timezone.utc)

                db.session.add(
                    SolarHealthReading(
                        facility_id=facility.id,
                        ts=reading_ts,
                        battery_soc_pct=round(soc, 1),
                        battery_soh_pct=round(soh, 1),
                        panel_status=panel_status,
                        battery_status=battery_status,
                        panel_temp_c=round(panel_temp_c, 1),
                        note="underperforming vs. trailing average" if is_trouble_month else None,
                        source_channel="seed",
                    )
                )
                rows_inserted += 2

        db.session.commit()
        click.echo(
            f"seeded {rows_inserted} solar rows across {len(facilities)} facilit(y/ies) "
            f"(install_capacity_kw set where it was null)"
        )
