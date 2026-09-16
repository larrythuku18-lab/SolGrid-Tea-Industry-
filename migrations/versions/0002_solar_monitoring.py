"""Solar generation health monitoring: panel/battery telemetry.

Deviation from the architecture doc: §9 build sequencing step 6 says
solar-generation ingestion should wait "only once panels are actually
contracted at either factory" — neither Kipchabo nor Gatitu has contracted
panels yet. Built ahead of that for a presentation, at the user's explicit
request, seeded with synthetic data (see `flask seed-solar-demo`) — not
real telemetry. Real ESP32 firmware and hardware remain a later step; this
only adds the schema and read path so the demo has somewhere real to land
data once that firmware exists.

Plain table, not a hypertable — telemetry volume from a demo/seed source
is tiny. Worth revisiting once real ESP32 readings arrive at whatever
frequency the firmware actually pushes at.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE solar_health_reading (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            facility_id UUID NOT NULL REFERENCES facility(id),
            organization_id UUID NOT NULL REFERENCES organization(id),
            ts TIMESTAMPTZ NOT NULL,
            battery_soc_pct NUMERIC
                CHECK (battery_soc_pct IS NULL OR (battery_soc_pct >= 0 AND battery_soc_pct <= 100)),
            battery_soh_pct NUMERIC
                CHECK (battery_soh_pct IS NULL OR (battery_soh_pct >= 0 AND battery_soh_pct <= 100)),
            panel_status TEXT NOT NULL
                CHECK (panel_status IN ('normal', 'underperforming', 'fault')),
            battery_status TEXT NOT NULL
                CHECK (battery_status IN ('normal', 'degraded', 'fault')),
            panel_temp_c NUMERIC,
            note TEXT,
            source_channel TEXT NOT NULL
                CHECK (source_channel IN ('esp32', 'manual', 'seed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_solar_health_reading_facility_ts
            ON solar_health_reading(facility_id, ts);
        """
    )

    # Same derive-don't-trust pattern as every other facility-scoped table —
    # set_organization_id_from_facility() already exists from 0001.
    op.execute(
        """
        CREATE TRIGGER trg_solar_health_reading_org_id
            BEFORE INSERT OR UPDATE OF facility_id ON solar_health_reading
            FOR EACH ROW EXECUTE FUNCTION set_organization_id_from_facility();
        """
    )

    op.execute("ALTER TABLE solar_health_reading ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE solar_health_reading FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON solar_health_reading
            USING (organization_id = current_org_id())
            WITH CHECK (organization_id = current_org_id());
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON solar_health_reading TO solgrid_app;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS solar_health_reading;")
