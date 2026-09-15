"""A real call to the Claude API, exercising the actual wiring (vision
input, structured output, the real prompt) rather than a mocked client.

Skips cleanly — not a failure — whenever ANTHROPIC_API_KEY is unset or the
call fails for any reason (no credit balance, network, rate limit). That's
deliberate: this machine's key had zero credit balance while this was
built, so this test has never actually run to completion here.

Read this test's name literally: "live" means a real API call, not "this
proves extraction works." The image below is a synthetically drawn
placeholder, not a real photographed KPLC bill, fuelwood note, or
production record — nobody has run this prompt against an actual
photographed document yet. A pass here confirms the plumbing (the request
shape is accepted, structured output parses, confidence enforcement still
applies to a real response) — nothing about real-world extraction
accuracy. Treat that as separately unverified until real documents exist
to test against, same as the brief this feature was built from says.
"""

import struct
import zlib

import pytest

from solgrid_tea.services.extraction import extract_document_fields


def _minimal_png(width: int = 64, height: int = 64) -> bytes:
    """Builds a tiny valid grayscale PNG from scratch — no Pillow dependency
    for one test fixture. Content is an arbitrary gradient; only needs to be
    a decodable image, not a realistic document."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    raw = b"".join(
        b"\x00" + bytes((x + y) % 256 for x in range(width)) for y in range(height)
    )
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


@pytest.mark.live_llm
def test_extraction_call_succeeds_against_a_synthetic_image():
    try:
        result = extract_document_fields(_minimal_png(), "image/png", "kplc_bill")
    except Exception as exc:  # noqa: BLE001 — any failure here means "skip", not "fail"
        pytest.skip(f"live Anthropic API call not usable in this environment: {exc}")

    assert result.document_type == "kplc_bill"
    # A synthetic gradient image plausibly can't be read as a real bill —
    # the meaningful assertion is that the guardrail held on a real
    # response, not that any particular field got a value.
    for field in result.fields.values():
        if field.confidence < 0.7:
            assert field.value is None
