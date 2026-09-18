"""Fetches and caches real daily solar irradiance per facility — see
migrations/0003's docstring for why this is cached rather than looked up
live from the read path.

Open-Meteo's archive API (https://open-meteo.com), not a paid provider:
no API key, no signup, and its ERA5-based reanalysis has global coverage
including East Africa. That directly matters here — the earlier "how many
API keys do I need" question is answered "zero more" for this feature.
Stdlib `urllib.request`, not a new HTTP-client dependency — one GET, no
auth, not worth a requirements.txt line.
"""

import json
import urllib.error
import urllib.request
from datetime import date

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE = "open-meteo"
REQUEST_TIMEOUT_S = 20
MJ_PER_KWH = 3.6  # 1 kWh = 3.6 MJ — Open-Meteo reports shortwave_radiation_sum in MJ/m^2/day


class IrradianceFetchError(Exception):
    """Network/HTTP/parse failure talking to the irradiance provider.
    Callers decide whether that's fatal — the sync CLI logs and moves on
    to the next facility rather than losing a whole run over one lookup."""


def fetch_daily_ghi(
    latitude: float, longitude: float, start_date: date, end_date: date
) -> dict[date, float]:
    """Daily global horizontal irradiance (kWh/m^2/day) for a location and
    date range, keyed by date. Open-Meteo omits a day from the response
    (rather than returning a null) when its reanalysis hasn't caught up to
    it yet — very recent days routinely aren't in the result at all, which
    is why this returns a dict a caller can safely index into rather than
    a positional list."""
    params = (
        f"latitude={latitude}&longitude={longitude}"
        f"&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        "&daily=shortwave_radiation_sum&timezone=UTC"
    )
    url = f"{ARCHIVE_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_S) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise IrradianceFetchError(f"could not reach {ARCHIVE_URL}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IrradianceFetchError(f"unparseable response from {ARCHIVE_URL}: {exc}") from exc

    try:
        daily = payload["daily"]
        days = daily["time"]
        values_mj = daily["shortwave_radiation_sum"]
    except KeyError as exc:
        raise IrradianceFetchError(f"unexpected response shape from {ARCHIVE_URL}: {payload}") from exc

    result: dict[date, float] = {}
    for day_str, value_mj in zip(days, values_mj):
        if value_mj is None:
            continue
        result[date.fromisoformat(day_str)] = value_mj / MJ_PER_KWH
    return result
