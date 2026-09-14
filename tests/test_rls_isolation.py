"""Integration tests for the RLS design in migrations/0001_initial_schema.

Requires `docker compose up db` and DATABASE_URL/TEST_DATABASE_URL pointed
at the *restricted* solgrid_app role (not the owner) — that's the whole
point, since RLS is exactly what's being tested. Skipped automatically if
no database is reachable (see conftest.db_session).

Everything runs in one uncommitted transaction per test and is rolled back
by the db_session fixture's teardown, so this never leaves data behind in
whatever database it's pointed at.
"""

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


def _set_org_context(session, org_id: uuid.UUID) -> None:
    # SET LOCAL doesn't accept bind parameters; set_config() does.
    session.execute(text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)})


def _create_org_with_facility(session, org_id: uuid.UUID) -> uuid.UUID:
    _set_org_context(session, org_id)
    session.execute(
        text("INSERT INTO organization (id, name) VALUES (:id, :name)"),
        {"id": str(org_id), "name": f"org-{org_id}"},
    )
    facility_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO facility (id, organization_id, name) VALUES (:id, :org_id, 'F1')"
        ),
        {"id": str(facility_id), "org_id": str(org_id)},
    )
    return facility_id


def test_org_only_sees_its_own_facility(db_session):
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    facility_a = _create_org_with_facility(db_session, org_a)
    facility_b = _create_org_with_facility(db_session, org_b)

    _set_org_context(db_session, org_a)
    visible_ids = {str(r[0]) for r in db_session.execute(text("SELECT id FROM facility"))}

    assert str(facility_a) in visible_ids
    assert str(facility_b) not in visible_ids


def test_cross_tenant_energy_reading_insert_is_rejected(db_session):
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    _create_org_with_facility(db_session, org_a)
    facility_b = _create_org_with_facility(db_session, org_b)

    _set_org_context(db_session, org_a)
    with pytest.raises(Exception):
        db_session.execute(
            text(
                "INSERT INTO energy_reading "
                "(facility_id, reading_type, period_start, period_end, quantity, unit, source_channel) "
                "VALUES (:facility_id, 'grid_electricity', '2026-01-01', '2026-01-31', "
                "100, 'kWh', 'manual')"
            ),
            {"facility_id": str(facility_b)},
        )
        db_session.flush()


def test_unset_org_context_sees_nothing_not_everything(db_session):
    org_a = uuid.uuid4()
    _create_org_with_facility(db_session, org_a)

    # A fresh SAVEPOINT with no app.org_id set at all must fail closed.
    with db_session.begin_nested():
        db_session.execute(text("RESET app.org_id"))
        rows = db_session.execute(text("SELECT id FROM facility")).fetchall()
        assert rows == []
