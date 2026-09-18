"""Unit tests for irradiance_sync — mocked HTTP, no network or database
needed, same pattern as test_extraction.py mocking anthropic.Anthropic."""

import json
import urllib.error
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from solgrid_tea.services.irradiance_sync import IrradianceFetchError, fetch_daily_ghi


def _mock_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


def test_fetch_daily_ghi_converts_mj_to_kwh():
    payload = {
        "daily": {
            "time": ["2026-08-01", "2026-08-02"],
            "shortwave_radiation_sum": [18.0, 21.6],
        }
    }
    with patch("solgrid_tea.services.irradiance_sync.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_response(payload)
        result = fetch_daily_ghi(-0.78, 35.34, date(2026, 8, 1), date(2026, 8, 2))

    # 18.0 MJ/m^2 / 3.6 = 5.0 kWh/m^2; 21.6 / 3.6 = 6.0
    assert result == {date(2026, 8, 1): pytest.approx(5.0), date(2026, 8, 2): pytest.approx(6.0)}


def test_fetch_daily_ghi_skips_null_days():
    # Open-Meteo returns null (not an entry) for days its reanalysis hasn't
    # caught up to — must not crash on that, and must not fabricate a value.
    payload = {"daily": {"time": ["2026-08-01", "2026-08-02"], "shortwave_radiation_sum": [18.0, None]}}
    with patch("solgrid_tea.services.irradiance_sync.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_response(payload)
        result = fetch_daily_ghi(-0.78, 35.34, date(2026, 8, 1), date(2026, 8, 2))

    assert list(result.keys()) == [date(2026, 8, 1)]


def test_fetch_daily_ghi_raises_on_network_failure():
    with patch("solgrid_tea.services.irradiance_sync.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("no route to host")
        with pytest.raises(IrradianceFetchError):
            fetch_daily_ghi(-0.78, 35.34, date(2026, 8, 1), date(2026, 8, 2))


def test_fetch_daily_ghi_raises_on_unexpected_shape():
    with patch("solgrid_tea.services.irradiance_sync.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_response({"error": "bad request"})
        with pytest.raises(IrradianceFetchError):
            fetch_daily_ghi(-0.78, 35.34, date(2026, 8, 1), date(2026, 8, 2))
