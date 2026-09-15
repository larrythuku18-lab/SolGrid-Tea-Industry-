"""Unit tests for the extraction service's guardrails — confidence-floor
enforcement and the document_type override — with the Anthropic client
mocked out. These never call the real API and never spend a token.

What these do NOT cover: whether the prompt actually gets good readings
off a real photographed KPLC bill, fuelwood note, or production record.
No real photographed document was available to test against while
building this — only these mocked-response tests and a synthetic-image
live-call check (see test_extraction_live.py) exist right now. Treat
extraction quality as unverified until it's run against real documents.
"""

from types import SimpleNamespace
from unittest.mock import patch

from solgrid_tea.schemas.extraction import ExtractionResult
from solgrid_tea.services.extraction import extract_document_fields


def _fake_response(parsed: ExtractionResult):
    return SimpleNamespace(parsed_output=parsed)


def test_low_confidence_field_is_nulled_even_if_model_supplied_a_value():
    # Simulates the model not following the "below 0.7 means null" prompt
    # instruction — the defensive server-side enforcement must catch it
    # regardless, per the module's own stated belt-and-suspenders design.
    canned = ExtractionResult(
        document_type="kplc_bill",
        unreadable=False,
        fields={
            "kwh_consumed": {"value": "4200", "confidence": 0.4, "raw_text": "4200 kWh"},
            "cost_kes": {"value": "63000", "confidence": 0.95, "raw_text": "KES 63,000"},
        },
    )
    with patch("solgrid_tea.services.extraction.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.parse.return_value = _fake_response(canned)
        result = extract_document_fields(b"fake-bytes", "image/png", "kplc_bill")

    assert result.fields["kwh_consumed"].value is None
    assert result.fields["kwh_consumed"].confidence == 0.4
    assert result.fields["cost_kes"].value == "63000"


def test_document_type_is_forced_to_caller_value_not_trusted_from_model():
    # The model is asked to echo document_type back; this proves the
    # service never trusts that echo over what the caller already knows,
    # matching the prompt doc's wiring note about image_ref.
    canned = ExtractionResult(document_type="fuelwood_note", unreadable=False, fields={})
    with patch("solgrid_tea.services.extraction.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.parse.return_value = _fake_response(canned)
        result = extract_document_fields(b"fake-bytes", "image/jpeg", "kplc_bill")

    assert result.document_type == "kplc_bill"


def test_unreadable_result_passes_through_with_empty_fields():
    canned = ExtractionResult(document_type="production_record", unreadable=True, fields={})
    with patch("solgrid_tea.services.extraction.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.parse.return_value = _fake_response(canned)
        result = extract_document_fields(b"fake-bytes", "image/png", "production_record")

    assert result.unreadable is True
    assert result.fields == {}


def test_prompt_embeds_the_declared_document_type():
    from solgrid_tea.services.extraction import _PROMPT_TEMPLATE

    prompt = _PROMPT_TEMPLATE.format(document_type="fuelwood_note")
    assert "Document type for this call: fuelwood_note" in prompt
    assert '"document_type": "fuelwood_note"' in prompt


def test_api_status_error_becomes_domain_error():
    import anthropic

    from solgrid_tea.errors import DomainError

    with patch("solgrid_tea.services.extraction.anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.parse.side_effect = anthropic.APIStatusError(
            message="rate limited",
            response=SimpleNamespace(status_code=429, headers={}, request=SimpleNamespace()),
            body=None,
        )
        try:
            extract_document_fields(b"fake-bytes", "image/png", "kplc_bill")
            raised = False
        except DomainError as exc:
            raised = True
            assert exc.status_code == 502

    assert raised
