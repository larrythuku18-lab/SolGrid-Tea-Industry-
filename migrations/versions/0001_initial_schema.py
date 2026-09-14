"""Initial schema: tenancy, ledger, reference data, RLS.

Deviations from the architecture doc, and why:

- energy_reading uses period_start/period_end (DATE) instead of a single
  `ts` column. §2 of the doc defines `ts TIMESTAMPTZ`, but §3 explicitly
  requires period_start/period_end on every ledger record ("the ingestion
  layer should require a period_start/period_end... rather than a single
  timestamp") — the two sections contradict each other. This migration
  follows §3, since matching periods against production_record is the
  whole point of the ledger. period_start is the hypertable dimension.

- Every tenant table gets a direct `organization_id` column (populated by
  a BEFORE INSERT trigger for facility-scoped tables), rather than the
  doc's plan of scoping energy_reading/production_record/etc. by a
  subquery through facility. Two reasons: (1) tariff can have a NULL
  facility_id for an org-wide default rate, and a subquery-based policy
  keyed only on facility_id has no way to scope that NULL-facility row to
  a single org — it would be visible to every tenant; (2) a flat equality
  check is materially cheaper to evaluate per-row than a correlated
  subquery, on every query, forever.

- RLS policies use a current_org_id() helper — SELECT NULLIF(current_setting
  ('app.org_id', true), '')::uuid — instead of the doc's bare
  current_setting('app.org_id')::uuid. Two problems with the doc's version,
  both confirmed against a real Postgres instance while building this:
  (1) without missing_ok=true, any connection that queries a protected
  table before app.org_id is ever set (a migration, an admin script, a bug)
  gets a hard error instead of an empty result set; (2) on a connection
  where app.org_id *was* set earlier and later RESET (pooled connections
  reuse the same backend), Postgres reverts a custom placeholder GUC to
  '' — not NULL — so a bare ::uuid cast still throws. NULLIF(..., '')
  collapses both the never-set and the reset-to-blank cases to a real SQL
  NULL, which makes `organization_id = NULL` evaluate to false (row
  excluded) instead of raising, so the failure mode is always "see
  nothing," never a 500 that could be mistaken for "see everything works."

- Every tenant table has FORCE ROW LEVEL SECURITY, not just ENABLE. Plain
  ENABLE exempts the table owner from RLS; since Alembic migrations and
  admin tooling connect as the owner role, an accidental owner-role query
  would otherwise silently see every tenant's data.

- energy_content_factor is a new table, not in the doc. cost_kes/kg tea and
  energy-mix % require converting litres of diesel and m3 of fuelwood into
  a common energy unit, and that conversion factor is exactly the kind of
  number the doc's own principle (§0.2: versioned, sourced, never hardcoded
  in code) says shouldn't be a Python constant.

Revision ID: 0001
Revises:
Create Date: 2026-09-14
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    op.execute(
        """
        CREATE TABLE organization (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            sector TEXT NOT NULL DEFAULT 'tea',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE facility (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organization(id),
            name TEXT NOT NULL,
            county TEXT,
            install_capacity_kw NUMERIC,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_facility_organization_id ON facility(organization_id);
        """
    )

    op.execute(
        """
        CREATE TABLE app_user (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organization(id),
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin','operator','viewer')),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX ux_app_user_email_lower ON app_user (lower(email));
        CREATE INDEX ix_app_user_organization_id ON app_user(organization_id);
        """
    )

    op.execute(
        """
        CREATE TABLE production_record (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            facility_id UUID NOT NULL REFERENCES facility(id),
            organization_id UUID NOT NULL REFERENCES organization(id),
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            made_tea_kg NUMERIC NOT NULL CHECK (made_tea_kg > 0),
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (period_end >= period_start)
        );
        CREATE INDEX ix_production_record_facility_period
            ON production_record(facility_id, period_start);
        """
    )

    # Composite PK (id, period_start): TimescaleDB requires any unique or
    # primary key constraint on a hypertable to include the partitioning
    # column.
    op.execute(
        """
        CREATE TABLE energy_reading (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            period_start DATE NOT NULL,
            facility_id UUID NOT NULL REFERENCES facility(id),
            organization_id UUID NOT NULL REFERENCES organization(id),
            reading_type TEXT NOT NULL CHECK (
                reading_type IN ('grid_electricity','diesel','fuelwood','solar_generation')
            ),
            period_end DATE NOT NULL,
            quantity NUMERIC NOT NULL CHECK (quantity > 0),
            unit TEXT NOT NULL,
            cost_kes NUMERIC CHECK (cost_kes IS NULL OR cost_kes >= 0),
            moisture_pct NUMERIC CHECK (
                moisture_pct IS NULL OR (moisture_pct >= 0 AND moisture_pct <= 100)
            ),
            source_plantation TEXT,
            source_channel TEXT NOT NULL CHECK (
                source_channel IN ('esp32','modbus','oem_api','manual','sms')
            ),
            entered_by_user_id UUID REFERENCES app_user(id),
            entered_by_phone TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, period_start),
            CHECK (period_end >= period_start)
        );
        """
    )
    op.execute("SELECT create_hypertable('energy_reading', 'period_start');")
    op.execute(
        """
        CREATE INDEX ix_energy_reading_facility_period
            ON energy_reading(facility_id, period_start);
        CREATE INDEX ix_energy_reading_facility_type
            ON energy_reading(facility_id, reading_type);
        """
    )

    op.execute(
        """
        CREATE TABLE emission_factor (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fuel_type TEXT NOT NULL,
            kg_co2_per_unit NUMERIC NOT NULL,
            unit TEXT NOT NULL,
            effective_from DATE NOT NULL,
            methodology_note TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_emission_factor_fuel_effective
            ON emission_factor(fuel_type, effective_from);
        """
    )

    op.execute(
        """
        CREATE TABLE energy_content_factor (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fuel_type TEXT NOT NULL,
            kwh_per_unit NUMERIC NOT NULL,
            unit TEXT NOT NULL,
            effective_from DATE NOT NULL,
            methodology_note TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_energy_content_factor_fuel_effective
            ON energy_content_factor(fuel_type, effective_from);
        """
    )

    op.execute(
        """
        CREATE TABLE tariff (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organization(id),
            facility_id UUID REFERENCES facility(id),
            fuel_type TEXT NOT NULL,
            price_kes_per_unit NUMERIC NOT NULL,
            effective_from DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_tariff_org_fuel_effective
            ON tariff(organization_id, fuel_type, effective_from);
        """
    )

    op.execute(
        """
        CREATE TABLE scenario_run (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            facility_id UUID NOT NULL REFERENCES facility(id),
            organization_id UUID NOT NULL REFERENCES organization(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            assumptions JSONB NOT NULL,
            results JSONB NOT NULL,
            created_by_user_id UUID REFERENCES app_user(id)
        );
        CREATE INDEX ix_scenario_run_facility ON scenario_run(facility_id);
        """
    )

    op.execute(
        """
        CREATE TABLE report_snapshot (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            facility_id UUID NOT NULL REFERENCES facility(id),
            organization_id UUID NOT NULL REFERENCES organization(id),
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload JSONB NOT NULL,
            methodology_version TEXT NOT NULL,
            superseded_by UUID REFERENCES report_snapshot(id)
        );
        CREATE INDEX ix_report_snapshot_facility_period
            ON report_snapshot(facility_id, period_start, period_end);
        """
    )

    # organization_id on facility-scoped tables is derived, never
    # client-supplied. The SELECT inside runs as whatever role fired the
    # triggering INSERT — for the app's runtime role that means it is
    # itself subject to facility's RLS policy, so a facility_id belonging
    # to another tenant resolves to NULL here and gets rejected below,
    # rather than silently trusting a cross-tenant reference.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_organization_id_from_facility()
        RETURNS TRIGGER AS $$
        BEGIN
            SELECT organization_id INTO NEW.organization_id
            FROM facility WHERE id = NEW.facility_id;
            IF NEW.organization_id IS NULL THEN
                RAISE EXCEPTION 'facility_id % does not resolve to a visible organization',
                    NEW.facility_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table in ("production_record", "energy_reading", "scenario_run", "report_snapshot"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_org_id
                BEFORE INSERT OR UPDATE OF facility_id ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_organization_id_from_facility();
            """
        )

    # --- Row-level security -------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_org_id() RETURNS UUID
        LANGUAGE sql STABLE
        AS $$
            SELECT NULLIF(current_setting('app.org_id', true), '')::uuid;
        $$;
        """
    )

    tenant_tables_by_org_column = {
        "organization": "id",
        "facility": "organization_id",
        "app_user": "organization_id",
        "production_record": "organization_id",
        "energy_reading": "organization_id",
        "tariff": "organization_id",
        "scenario_run": "organization_id",
        "report_snapshot": "organization_id",
    }
    for table, org_column in tenant_tables_by_org_column.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING ({org_column} = current_org_id())
                WITH CHECK ({org_column} = current_org_id());
            """
        )
    # emission_factor and energy_content_factor are global reference data,
    # shared read-only by every tenant — deliberately no RLS.

    # --- Login lookup bypass -------------------------------------------------
    # There is no org context yet at login time (the whole point of logging
    # in is to discover which org an email belongs to), so a plain RLS-scoped
    # query on app_user can never find the row. SECURITY DEFINER narrows that
    # to exactly one query, exactly this shape — not a blanket RLS exemption.
    #
    # This function's owner must be able to bypass RLS (superuser, or an
    # explicit BYPASSRLS grant) for it to keep working now that app_user has
    # FORCE ROW LEVEL SECURITY applied. In this project's docker-compose dev
    # setup the migration-owner role is a Postgres superuser, so this works
    # out of the box; a production deployment where the owner role is NOT a
    # superuser must grant it BYPASSRLS explicitly (see scripts/bootstrap_db_roles.sql).
    op.execute(
        """
        CREATE FUNCTION auth_lookup_user(p_email TEXT)
        RETURNS TABLE(id UUID, organization_id UUID, password_hash TEXT, role TEXT, is_active BOOLEAN)
        SECURITY DEFINER
        SET search_path = public
        LANGUAGE sql
        AS $$
            SELECT id, organization_id, password_hash, role, is_active
            FROM app_user
            WHERE lower(email) = lower(p_email);
        $$;
        REVOKE ALL ON FUNCTION auth_lookup_user(TEXT) FROM PUBLIC;
        """
    )

    # --- Runtime role grants --------------------------------------------------
    # Redundant with the ALTER DEFAULT PRIVILEGES in bootstrap_db_roles.sql
    # (which covers tables created by the owner role after that script ran)
    # but kept explicit here so this migration is self-contained and correct
    # even run against a database where the bootstrap script's default-
    # privileges clause was skipped or predates this migration.
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            organization, facility, app_user, production_record, energy_reading,
            tariff, scenario_run, report_snapshot
            TO solgrid_app;
        GRANT SELECT ON emission_factor, energy_content_factor TO solgrid_app;
        GRANT EXECUTE ON FUNCTION auth_lookup_user(TEXT) TO solgrid_app;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_user(TEXT);")
    op.execute("DROP TABLE IF EXISTS report_snapshot;")
    op.execute("DROP TABLE IF EXISTS scenario_run;")
    op.execute("DROP TABLE IF EXISTS tariff;")
    op.execute("DROP TABLE IF EXISTS energy_content_factor;")
    op.execute("DROP TABLE IF EXISTS emission_factor;")
    op.execute("DROP TABLE IF EXISTS energy_reading;")
    op.execute("DROP TABLE IF EXISTS production_record;")
    op.execute("DROP TABLE IF EXISTS app_user;")
    op.execute("DROP TABLE IF EXISTS facility;")
    op.execute("DROP TABLE IF EXISTS organization;")
    op.execute("DROP FUNCTION IF EXISTS set_organization_id_from_facility();")
    op.execute("DROP FUNCTION IF EXISTS current_org_id();")
    # timescaledb extension intentionally left in place — dropping a shared
    # cluster extension from a migration downgrade is a bigger blast radius
    # than this migration should take responsibility for.
