"""Integration tests for the report_snapshot correction flow
(_resolve_superseded_snapshot in blueprints/report.py) — same fixture
pattern as test_report_engine.py. Needs a live database.

The full publish_report() endpoint isn't exercised here — the repo has no
HTTP-layer (client.post + JWT) tests anywhere yet, and adding that
scaffolding is out of scope for this one endpoint. _resolve_superseded_snapshot
holds all the new validation logic; the wiring around it in publish_report
(flush to get snapshot.id, then set superseded_by) is a few lines of glue
with nothing left to validate once this function is correct.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from solgrid_tea.blueprints.report import _resolve_superseded_snapshot
from solgrid_tea.errors import DomainError
from solgrid_tea.models import ReportSnapshot
from solgrid_tea.schemas.report import PublishReportRequest

pytestmark = pytest.mark.db


@pytest.fixture()
def facility(db_session):
    org_id = uuid.uuid4()
    db_session.execute(
        text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)}
    )
    db_session.execute(
        text("INSERT INTO organization (id, name) VALUES (:id, 'Gatitu Test')"),
        {"id": str(org_id)},
    )
    facility_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO facility (id, organization_id, name) VALUES (:id, :org_id, 'Gatitu')"),
        {"id": str(facility_id), "org_id": str(org_id)},
    )
    return facility_id


def _insert_snapshot(
    session,
    facility_id,
    period_start=date(2026, 1, 1),
    period_end=date(2026, 1, 31),
    superseded_by=None,
) -> uuid.UUID:
    snapshot_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO report_snapshot "
            "(id, facility_id, period_start, period_end, payload, methodology_version, superseded_by) "
            "VALUES (:id, :facility_id, :start, :end, '{}'::jsonb, 'solgrid-tea-report-v1', :superseded_by)"
        ),
        {
            "id": str(snapshot_id),
            "facility_id": str(facility_id),
            "start": period_start,
            "end": period_end,
            "superseded_by": str(superseded_by) if superseded_by else None,
        },
    )
    return snapshot_id


def _request(facility_id, supersedes=None, **overrides):
    kwargs = dict(
        facility_id=facility_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        supersedes=supersedes,
    )
    kwargs.update(overrides)
    return PublishReportRequest(**kwargs)


def test_no_supersedes_returns_none(db_session, facility):
    result = _resolve_superseded_snapshot(_request(facility))
    assert result is None


def test_valid_supersede_returns_the_snapshot(db_session, facility):
    old_id = _insert_snapshot(db_session, facility)
    db_session.flush()

    result = _resolve_superseded_snapshot(_request(facility, supersedes=old_id))

    assert isinstance(result, ReportSnapshot)
    assert result.id == old_id


def test_unknown_snapshot_id_is_404(db_session, facility):
    with pytest.raises(DomainError) as exc_info:
        _resolve_superseded_snapshot(_request(facility, supersedes=uuid.uuid4()))
    assert exc_info.value.status_code == 404


def test_already_superseded_snapshot_is_409(db_session, facility):
    newer_id = _insert_snapshot(db_session, facility)
    old_id = _insert_snapshot(db_session, facility, superseded_by=newer_id)
    db_session.flush()

    with pytest.raises(DomainError) as exc_info:
        _resolve_superseded_snapshot(_request(facility, supersedes=old_id))
    assert exc_info.value.status_code == 409


def test_mismatched_period_is_422(db_session, facility):
    old_id = _insert_snapshot(
        db_session, facility, period_start=date(2025, 12, 1), period_end=date(2025, 12, 31)
    )
    db_session.flush()

    with pytest.raises(DomainError) as exc_info:
        _resolve_superseded_snapshot(_request(facility, supersedes=old_id))
    assert exc_info.value.status_code == 422


def test_mismatched_facility_is_422(db_session, facility):
    other_facility = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO facility (id, organization_id, name) VALUES (:id, current_org_id(), 'Other')"),
        {"id": str(other_facility)},
    )
    old_id = _insert_snapshot(db_session, other_facility)
    db_session.flush()

    with pytest.raises(DomainError) as exc_info:
        _resolve_superseded_snapshot(_request(facility, supersedes=old_id))
    assert exc_info.value.status_code == 422
