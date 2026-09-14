import uuid
from datetime import date

import click
from sqlalchemy import text

from solgrid_tea.extensions import db
from solgrid_tea.models import AppUser, EmissionFactor, EnergyContentFactor, Facility, Organization


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
    def seed_reference_data():
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
        today = date.today()

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
