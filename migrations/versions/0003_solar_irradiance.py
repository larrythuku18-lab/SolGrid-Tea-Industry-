"""Facility coordinates + a cached daily irradiance table, for
weather-adjusted expected generation.

Why this exists: solar_insights' underperformance check (migration 0002)
could only compare a site against its own trailing average — it couldn't
tell a cloudy week from a failing inverter. Fixing that needs real solar
irradiance for the site's location, which this adds a place to cache.

Cached, not fetched live: `generation_vs_consumption_series` and
`solar_health_summary` are called on every live-stream poll (every few
seconds — see solar_live.py). Hitting a third-party weather API that often
would be slow, rate-limit-risky, and make the live feed's poll loop
depend on a network call it has no business making. `flask
sync-solar-irradiance` populates this table on a schedule (like a cron job
would in production); the read path only ever queries Postgres.

latitude/longitude are nullable and, per facility, approximate — see
cli.py's seed-solar-demo, which seeds a placeholder location for the
Kenyan tea highlands, not a verified GPS survey of either site.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE facility
            ADD COLUMN latitude NUMERIC CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
            ADD COLUMN longitude NUMERIC CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180));
        """
    )

    op.execute(
        """
        CREATE TABLE solar_irradiance_daily (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            facility_id UUID NOT NULL REFERENCES facility(id),
            organization_id UUID NOT NULL REFERENCES organization(id),
            day DATE NOT NULL,
            ghi_kwh_per_m2 NUMERIC NOT NULL CHECK (ghi_kwh_per_m2 >= 0),
            source TEXT NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (facility_id, day)
        );
        CREATE INDEX ix_solar_irradiance_daily_facility_day
            ON solar_irradiance_daily(facility_id, day);
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_solar_irradiance_daily_org_id
            BEFORE INSERT OR UPDATE OF facility_id ON solar_irradiance_daily
            FOR EACH ROW EXECUTE FUNCTION set_organization_id_from_facility();
        """
    )

    op.execute("ALTER TABLE solar_irradiance_daily ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE solar_irradiance_daily FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON solar_irradiance_daily
            USING (organization_id = current_org_id())
            WITH CHECK (organization_id = current_org_id());
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON solar_irradiance_daily TO solgrid_app;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS solar_irradiance_daily;")
    op.execute("ALTER TABLE facility DROP COLUMN IF EXISTS latitude;")
    op.execute("ALTER TABLE facility DROP COLUMN IF EXISTS longitude;")
