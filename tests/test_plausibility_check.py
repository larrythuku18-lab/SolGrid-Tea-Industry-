from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from solgrid_tea.schemas.report import PeriodSummary
from solgrid_tea.services.plausibility_check import _LLMPlausibilityOutput, run_plausibility_check


def _summary(**overrides) -> PeriodSummary:
    kwargs = dict(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        made_tea_kg=5000.0,
        electricity_kwh=10000.0,
        electricity_cost_kes=150000.0,
        fuelwood_volume_m3=60.0,
        fuelwood_cost_kes=240000.0,
        cost_per_kg_kes=78.0,
    )
    kwargs.update(overrides)
    return PeriodSummary(**kwargs)


def test_no_trailing_history_skips_the_call_entirely():
    with patch("solgrid_tea.services.plausibility_check.anthropic.Anthropic") as mock_anthropic:
        result = run_plausibility_check(_summary(), trailing=[])

    mock_anthropic.assert_not_called()
    assert result.skipped is True
    assert result.flagged is False
    assert result.note is None


def test_call_happens_when_trailing_history_exists():
    canned = _LLMPlausibilityOutput(flagged=False, note=None)
    with patch("solgrid_tea.services.plausibility_check.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.parse.return_value = SimpleNamespace(
            parsed_output=canned
        )
        result = run_plausibility_check(_summary(), trailing=[_summary()])

    mock_anthropic.return_value.messages.parse.assert_called_once()
    assert result.skipped is False
    assert result.flagged is False


def test_flagged_result_is_passed_through():
    canned = _LLMPlausibilityOutput(
        flagged=True, note="fuelwood_cost_kes rose 40% while made_tea_kg was flat"
    )
    with patch("solgrid_tea.services.plausibility_check.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.parse.return_value = SimpleNamespace(
            parsed_output=canned
        )
        result = run_plausibility_check(_summary(), trailing=[_summary()])

    assert result.flagged is True
    assert result.note == "fuelwood_cost_kes rose 40% while made_tea_kg was flat"
    assert result.skipped is False
