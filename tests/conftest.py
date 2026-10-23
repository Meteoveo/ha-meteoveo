"""Shared fixtures for the Home Assistant test harness."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

STATION_VIEW = {
    "station": {"name": "Garden", "lat": 38.98, "lon": -0.17},
    "health": {"findings": []},
    "model": {"status": "collecting", "samples": 0, "samplesNeeded": 10, "daysRemaining": 10},
    "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None},
}

# A home view (contract v1) with every block present. Example values only.
HOME_VIEW = {
    "v": 1,
    "issuedAt": "2026-10-23T12:50:16Z",
    "level": "free",
    "place": {"name": "Villa Ejemplo", "lat": 38.92, "lon": -0.26, "elevationM": 173},
    "current": {
        "at": "2026-10-23T12:41:00Z",
        "basis": "station",
        "condition": "partlycloudy",
        "iconKey": "fatyolfelhos",
        "isDaylight": True,
        "tempC": 23.1,
        "humidityPct": 44,
        "pressureHpa": None,
        "windMs": 2.6,
        "gustMs": 9.7,
        "windBearingDeg": 113,
        "precipMm": None,
    },
    "nextHour": {
        "issuedAt": "2026-10-23T12:48:00Z",
        "ageMinutes": 2,
        "rainNow": False,
        "rainSoon": True,
        "rainStartsAt": "2026-10-23T13:20:00Z",
        "rainEndsAt": None,
        "steps": [
            {"at": "2026-10-23T12:50:00Z", "leadMinutes": 0, "band": "none",
             "source": "radar", "uncertain": False},
            {"at": "2026-10-23T13:20:00Z", "leadMinutes": 30, "band": "light",
             "source": "model", "uncertain": True},
        ],
    },
    "hourly": [
        {"at": "2026-10-23T13:00:00Z", "condition": "partlycloudy", "iconKey": "fatyolfelhos",
         "isDaylight": True, "tempC": 23.0, "feelsLikeC": 23, "humidityPct": 40, "precipMm": 0,
         "precipProbPct": 0, "windMs": 2.8, "gustMs": 6.2, "windBearingDeg": 315, "uvIndex": 3},
        {"at": "2026-10-23T19:00:00Z", "condition": "clear-night", "iconKey": "napos",
         "isDaylight": False, "tempC": 17.5, "feelsLikeC": None, "humidityPct": 60,
         "precipMm": None, "precipProbPct": 10, "windMs": 1.0, "gustMs": None,
         "windBearingDeg": 270, "uvIndex": 0},
    ],
    "daily": [
        {"date": "2026-10-23", "condition": "partlycloudy", "iconKey": "reszben_felhos",
         "tempMaxC": 24, "tempMinC": 13, "precipMm": 0, "precipProbPct": 0, "windMs": 4.2,
         "gustMs": None, "windBearingDeg": 270, "uvIndex": 3,
         "sunrise": "2026-10-23T06:18:30Z", "sunset": "2026-10-23T17:11:38Z", "trend": False},
        {"date": "2026-10-31", "condition": "rainy", "iconKey": "eso",
         "tempMaxC": 20, "tempMinC": 12, "precipMm": 4, "precipProbPct": None, "windMs": 5,
         "gustMs": None, "windBearingDeg": None, "uvIndex": None,
         "sunrise": None, "sunset": None, "trend": True},
    ],
    "warnings": [
        {"level": "yellow", "phenomenon": "PR", "phenomenonName": "Lluvias",
         "probability": "40%-70%", "headline": "Aviso amarillo por lluvias",
         "onset": "2026-10-23T15:00:00Z", "expires": "2026-10-23T23:59:00Z"},
    ],
    "attribution": "Datos: © AEMET, MeteoVeo.",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(hass, enable_custom_integrations):
    """Load the integration from custom_components during tests.

    The integration depends on ``http`` and ``frontend`` (it serves its card).
    The test harness has no frontend build, so both are marked as already
    loaded; the card registration itself is tested separately.
    """
    hass.config.components.update({"http", "frontend"})
    yield


@pytest.fixture(autouse=True)
def mock_home_view():
    """Every setup also reads the home view; answer it unless a test overrides."""
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(copy.deepcopy(HOME_VIEW), '"etag-1"')),
    ) as mocked:
        yield mocked


@pytest.fixture
def mock_station_view():
    """Patch the network call the config flow makes."""
    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(return_value=STATION_VIEW),
    ) as mocked:
        yield mocked
