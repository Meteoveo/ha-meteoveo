"""Config flow, exercised through Home Assistant itself."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.meteoveo.client import InvalidCredentials, ServiceUnavailable
from custom_components.meteoveo.const import (
    CONF_MEASUREMENTS,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DOMAIN,
)

CREDENTIALS = {CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key-value"}


async def start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_full_setup_creates_an_entry(hass: HomeAssistant, mock_station_view) -> None:
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["step_id"] == "measurements"

    # Nothing selected: a station with no matching entities must still finish.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garden"
    assert result["data"] == CREDENTIALS
    assert result["options"] == {CONF_MEASUREMENTS: {}}


async def test_credentials_are_checked_before_the_entry_is_created(
    hass: HomeAssistant, mock_station_view
) -> None:
    result = await start(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    mock_station_view.assert_awaited_once()


@pytest.mark.parametrize(
    "failure,expected",
    [
        (InvalidCredentials("no"), "invalid_auth"),
        (ServiceUnavailable("down"), "cannot_connect"),
        (TimeoutError(), "unknown"),
    ],
)
async def test_failures_are_reported_distinctly(
    hass: HomeAssistant, failure, expected
) -> None:
    with patch(
        "custom_components.meteoveo.config_flow._verify", new=AsyncMock(side_effect=failure)
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_recovers_after_a_failed_attempt(hass: HomeAssistant) -> None:
    # A wrong key must not be a dead end: correcting it has to work without
    # restarting the flow.
    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(return_value={"station": {"name": "Garden"}}),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_station_cannot_be_added_twice(
    hass: HomeAssistant, mock_station_view
) -> None:
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    await hass.config_entries.flow.async_configure(result["flow_id"], {})

    # Same station, different case and padding: still the same station.
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATION_ID: "  mvexample1 ", CONF_STATION_KEY: "key-value"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_title_falls_back_to_the_station_id(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.meteoveo.config_flow._verify", new=AsyncMock(return_value={})
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["title"] == "MVEXAMPLE1"
