from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from solgrid_tea.schemas.report import PublishReportRequest, ReportPayload
from solgrid_tea.services.report_engine import external_payload_view

FACILITY_ID = uuid4()


def test_publish_request_rejects_inverted_period():
    with pytest.raises(ValidationError):
        PublishReportRequest(
            facility_id=FACILITY_ID, period_start=date(2026, 2, 1), period_end=date(2026, 1, 1)
        )


def test_publish_request_override_reason_is_optional():
    req = PublishReportRequest(
        facility_id=FACILITY_ID, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31)
    )
    assert req.override_reason is None


def test_external_payload_strips_cost_and_production_figures():
    internal = ReportPayload(
        facility_id=FACILITY_ID,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_made_tea_kg=5000.0,
        total_cost_kes=225000.0,
        total_energy_kwh=15000.0,
        cost_per_kg_tea_kes=45.0,
        kwh_per_kg_tea=3.0,
        energy_mix_pct={"grid_electricity": 70.0, "diesel": 30.0},
        total_emissions_tco2=1.65,
        emissions_by_type_tco2={"grid_electricity": 1.1, "diesel": 0.55},
    )
    external = external_payload_view(internal, "solgrid-tea-report-v1")
    dumped = external.model_dump()

    # no raw KES anywhere, no production/cost-derived figures
    assert "total_cost_kes" not in dumped
    assert "cost_per_kg_tea_kes" not in dumped
    assert "total_made_tea_kg" not in dumped
    assert "total_energy_kwh" not in dumped
    assert "kwh_per_kg_tea" not in dumped

    # the curated subset survives intact
    assert external.energy_mix_pct == {"grid_electricity": 70.0, "diesel": 30.0}
    assert external.total_emissions_tco2 == 1.65
    assert external.emissions_by_type_tco2 == {"grid_electricity": 1.1, "diesel": 0.55}
    assert external.methodology_version == "solgrid-tea-report-v1"
    assert external.verification_status == "self_reported"
