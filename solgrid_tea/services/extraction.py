"""Photo-to-ledger-field extraction assist.

Implements SolGrid-Tea-AI-Prompts.md §1 exactly as written. This is an
assist, not a write path: it proposes field values for a human to review
and correct, then submit through the existing, unchanged
/api/v1/ledger/energy-readings and /production-records endpoints — this
module never writes to energy_reading or production_record itself, and
nothing it returns is persisted. The photo is held in memory only for the
duration of the API call and is never stored, logged, or written to disk.

Below-0.7-confidence-means-null is enforced twice: once by instruction in
the prompt itself, and once defensively in code after the response comes
back. Belt and suspenders — correctness here shouldn't depend solely on
the model having followed an instruction.
"""

import base64

import anthropic

from solgrid_tea.errors import DomainError
from solgrid_tea.schemas.extraction import DocumentType, ExtractionResult

MODEL = "claude-opus-5"

CONFIDENCE_FLOOR = 0.7

_PROMPT_TEMPLATE = """You are a document field extractor for SolGrid's tea-factory energy
ledger. You are given one photographed document and its declared type.
Extract only the fields defined for that type. Do not infer a different
document type from what's declared, and do not extract fields that
don't belong to it.

Document type for this call: {document_type}

Field definitions by type:

kplc_bill: period_start (date), period_end (date), kwh_consumed
(number), cost_kes (number)

fuelwood_note: delivery_date (date), volume (number), unit (string, as
written — e.g. "m3", "lorries", "loads" — do not convert units
yourself), moisture_pct (number, nullable — often absent from the
note), source_plantation (string, nullable)

production_record: period_start (date), period_end (date), made_tea_kg
(number)

For each field:
- Transcribe exactly what you read into raw_text, even if you're
  unsure.
- Set value to your best reading, or null if you cannot read it with
  reasonable confidence.
- Set confidence between 0 and 1. Below 0.7, set value to null
  regardless of what you think you see — a blank field a person fills
  in is better than a wrong number a person doesn't check. Reserve
  confidence above 0.9 for text that is unambiguous and clearly
  legible.
- Never fabricate a plausible-looking value for a field you cannot
  actually read.

If the photo does not appear to match the declared document type, or is
too degraded to attempt extraction at all, set unreadable to true and
return an empty fields object rather than guessing at content that
isn't there.

Assume exactly one document per photo. If the image shows more than
one, extract only the clearest one and set unreadable to true — do not
merge fields from multiple documents into one result.

Respond with only this JSON object. No prose before or after it.

{{
  "document_type": "{document_type}",
  "unreadable": false,
  "fields": {{
    "<field_name>": {{"value": null, "confidence": 0.0, "raw_text": null}}
  }}
}}"""


def extract_document_fields(
    image_bytes: bytes, media_type: str, document_type: DocumentType
) -> ExtractionResult:
    prompt = _PROMPT_TEMPLATE.format(document_type=document_type)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            output_format=ExtractionResult,
        )
    except anthropic.APIStatusError as exc:
        raise DomainError(f"extraction service error: {exc.message}", status_code=502) from exc
    except anthropic.APIConnectionError as exc:
        raise DomainError("extraction service unreachable", status_code=502) from exc

    result = response.parsed_output

    # document_type is already known to the caller — don't trust the model's
    # echo of it, same reasoning as image_ref in the prompt doc's wiring note.
    result.document_type = document_type

    for field in result.fields.values():
        if field.confidence < CONFIDENCE_FLOOR:
            field.value = None

    return result
