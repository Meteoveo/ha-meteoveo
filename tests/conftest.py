"""Shared fixtures for the Home Assistant test harness."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

STATION_VIEW = {
    "station": {"name": "Garden", "lat": 38.98, "lon": -0.17},
    "health": {"findings": []},
    "model": {"status": "collecting", "samples": 0, "samplesNeeded": 10, "daysRemaining": 10},
    "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components during tests."""
    yield


@pytest.fixture
def mock_station_view():
    """Patch the network call the config flow makes."""
    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(return_value=STATION_VIEW),
    ) as mocked:
        yield mocked
