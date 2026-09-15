from typing import Literal

from pydantic import BaseModel, Field

DocumentType = Literal["kplc_bill", "fuelwood_note", "production_record"]

DOCUMENT_TYPES: tuple[DocumentType, ...] = ("kplc_bill", "fuelwood_note", "production_record")


class ExtractedField(BaseModel):
    # Always a string, never typed per-field (date/number/etc.) — this is a
    # best-effort transcription for a human to review and correct, not a
    # value that goes anywhere near a database. Real typing/validation
    # happens where it always has: the existing EnergyReadingCreate /
    # ProductionRecordCreate schemas, when a person submits the reviewed
    # form through the unchanged /api/v1/ledger write endpoints.
    value: str | None = None
    confidence: float = Field(ge=0, le=1)
    raw_text: str | None = None


class ExtractionResult(BaseModel):
    document_type: DocumentType
    # SolGrid-Tea-AI-Prompts.md §1: signals a mismatched or unreadable photo
    # without forcing a guess into every field.
    unreadable: bool = False
    fields: dict[str, ExtractedField] = Field(default_factory=dict)
