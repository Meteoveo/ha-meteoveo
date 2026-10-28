"""Re-authentication and changing the measurement mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoveo.client import InvalidCredentials
from custom_components.meteoveo.const import (
    CONF_MEASUREMENTS,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DOMAIN,
)

ENTRY_DATA = {CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "old-key"}
VIEW = {"station": {"name": "Garden"}, "health": {"findings": []},
        "model": {"status": "collecting", "samples": 0, "samplesNeeded": 10, "daysRemaining": 10},
        "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None}}


def make_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id="mvexample1", options=options or {}
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth_replaces_the_key_without_reinstalling(hass: HomeAssistant) -> None:
    entry = make_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.meteoveo.config_flow._verify", new=AsyncMock(return_value=VIEW)
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_STATION_KEY: "new-key"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_STATION_KEY] == "new-key"
    # The station id is untouched, so entity history is not orphaned.
    assert entry.data[CONF_STATION_ID] == "MVEXAMPLE1"


async def test_reauth_reports_a_key_that_is_still_wrong(hass: HomeAssistant) -> None:
    entry = make_entry(hass)
    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_STATION_KEY: "still-wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_STATION_KEY] == "old-key"


async def test_options_flow_stores_the_selection(hass: HomeAssistant) -> None:
    entry = make_entry(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=VIEW),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"
        # A station-key entry has only the measurement mapping to change.
        assert result["menu_options"] == ["measurements", "visibility"]
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "measurements"}
        )
        assert result["step_id"] == "measurements"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"temperature": "sensor.outside_temperature"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_MEASUREMENTS] == {"temperature": "sensor.outside_temperature"}


async def test_options_flow_accepts_an_empty_selection(hass: HomeAssistant) -> None:
    # Clearing every measurement is a legitimate choice, not an error.
    entry = make_entry(hass, options={CONF_MEASUREMENTS: {"temperature": "sensor.t"}})
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=VIEW),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "measurements"}
        )
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert entry.options[CONF_MEASUREMENTS] == {}
