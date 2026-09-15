"""Pre-publish plausibility check — SolGrid-Tea-AI-Prompts.md §2, the one
place an LLM belongs in the reporting feature: one line, only for a
genuine deviation from trend, never running commentary.

Runs only when there's at least one trailing period with real data to
compare against. With none — true for both NTZDC facilities today, per
the prompt doc's own "Before any of this is production ready" section —
a trend comparison is structurally meaningless, so this skips the call
entirely rather than asking the model to judge against nothing. Skipping
is not the same as "checked and clean": see PlausibilityCheckResult.skipped.
"""

import json

import anthropic
from pydantic import BaseModel

from solgrid_tea.errors import DomainError
from solgrid_tea.schemas.report import PeriodSummary, PlausibilityCheckResult

MODEL = "claude-opus-5"


class _LLMPlausibilityOutput(BaseModel):
    """What the model actually produces — deliberately narrower than
    PlausibilityCheckResult. `skipped` is a server-side concept (whether
    the call happened at all); asking the model to fill it in would be
    asking it a question that isn't its to answer."""

    flagged: bool
    note: str | None

_PROMPT_TEMPLATE = """You review one period's computed energy figures for a tea factory
before they're published. Your only job is to flag anything that looks
genuinely unusual against the recent trend — not to restate the
numbers, not to narrate normal variation.

Input for this period:
{period_summary_json}

This includes made_tea_kg, electricity_kwh, electricity_cost_kes,
fuelwood_volume_m3, fuelwood_cost_kes, and cost_per_kg_kes for this
period and for each of the trailing 6 periods.

Flag something only if:
- A figure has moved more than the trailing average would predict, AND
- The move isn't explained by a proportional change in made_tea_kg (a
  jump in fuelwood volume alongside a matching jump in production is
  normal — don't flag it)
- You can name the specific figure and the specific deviation in one
  sentence, with actual numbers from the input, not a vague impression

If nothing clears that bar, set flagged to false and note to null.
Most periods should not be flagged — this is a check for genuine
outliers, not running commentary. Flag something because it's actually
anomalous against this factory's own history, never because it merely
seems worth mentioning.

Respond with only this JSON object, no prose before or after it:

{{
  "flagged": false,
  "note": null
}}"""


def run_plausibility_check(
    current: PeriodSummary, trailing: list[PeriodSummary]
) -> PlausibilityCheckResult:
    if not trailing:
        return PlausibilityCheckResult(flagged=False, note=None, skipped=True)

    period_summary_json = json.dumps(
        {
            "current_period": current.model_dump(mode="json"),
            "trailing_periods": [p.model_dump(mode="json") for p in trailing],
        },
        indent=2,
    )
    prompt = _PROMPT_TEMPLATE.format(period_summary_json=period_summary_json)

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            output_format=_LLMPlausibilityOutput,
        )
    except anthropic.APIStatusError as exc:
        raise DomainError(
            f"plausibility check service error: {exc.message}", status_code=502
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise DomainError("plausibility check service unreachable", status_code=502) from exc

    llm_output = response.parsed_output
    return PlausibilityCheckResult(flagged=llm_output.flagged, note=llm_output.note, skipped=False)
