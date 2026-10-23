"""Entities, exercised through a real config entry setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoveo.client import InvalidCredentials, ServiceUnavailable
from custom_components.meteoveo.const import CONF_STATION_ID, CONF_STATION_KEY, DOMAIN

ENTRY_DATA = {CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key-value"}

READY_VIEW = {
    "station": {"name": "Garden", "lat": 38.98, "lon": -0.17},
    "health": {"findings": ["radiation-bias"]},
    "model": {"status": "ready", "model": "icon", "mae": 1.2, "bias": -0.3, "samples": 40},
    "upload": {"lastSeenAt": "2026-08-20T10:00:00+00:00", "acceptedCount": 7, "lastError": None},
}

COLLECTING_VIEW = {
    "station": {"name": "Garden", "lat": 38.98, "lon": -0.17},
    "health": {"findings": []},
    "model": {"status": "collecting", "samples": 3, "samplesNeeded": 10, "daysRemaining": 7},
    "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None},
}


async def setup_entry(hass: HomeAssistant, view: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="mvexample1")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=view),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_setup_creates_the_entities(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, READY_VIEW)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.garden_best_forecast_model") is not None
    assert hass.states.get("sensor.garden_accepted_uploads") is not None
    assert hass.states.get("sensor.garden_last_upload") is not None
    assert hass.states.get("binary_sensor.garden_sensor_problem") is not None


async def test_model_verdict_when_there_is_enough_history(hass: HomeAssistant) -> None:
    await setup_entry(hass, READY_VIEW)
    state = hass.states.get("sensor.garden_best_forecast_model")

    assert state.state == "icon"
    assert state.attributes["mean_absolute_error"] == 1.2
    assert state.attributes["samples"] == 40


async def test_model_verdict_counts_down_while_collecting(hass: HomeAssistant) -> None:
    # An empty value here would look like a fault; the countdown says the
    # station's own data is what is still missing.
    await setup_entry(hass, COLLECTING_VIEW)
    state = hass.states.get("sensor.garden_best_forecast_model")

    assert state.state == "collecting"
    assert state.attributes["days_remaining"] == 7
    assert state.attributes["samples_needed"] == 10


async def test_sensor_problem_reflects_the_findings(hass: HomeAssistant) -> None:
    await setup_entry(hass, READY_VIEW)
    state = hass.states.get("binary_sensor.garden_sensor_problem")

    assert state.state == "on"
    assert state.attributes["findings"] == ["radiation-bias"]


async def test_no_findings_means_no_problem(hass: HomeAssistant) -> None:
    await setup_entry(hass, COLLECTING_VIEW)
    assert hass.states.get("binary_sensor.garden_sensor_problem").state == "off"


async def test_upload_sensors(hass: HomeAssistant) -> None:
    await setup_entry(hass, READY_VIEW)
    assert hass.states.get("sensor.garden_accepted_uploads").state == "7"
    assert hass.states.get("sensor.garden_last_upload").state != "unknown"


async def test_entities_are_grouped_under_one_device(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    await setup_entry(hass, READY_VIEW)
    devices = dr.async_get(hass)
    device = devices.async_get_device(identifiers={(DOMAIN, "MVEXAMPLE1")})

    assert device is not None
    assert device.name == "Garden"


async def test_unique_ids_survive_a_key_rotation(hass: HomeAssistant) -> None:
    # Unique ids are built from the station id, which does not change when the
    # key is replaced -- so history is not orphaned by re-authentication.
    from homeassistant.helpers import entity_registry as er

    await setup_entry(hass, READY_VIEW)
    entities = er.async_get(hass)
    entry = entities.async_get("sensor.garden_accepted_uploads")

    assert entry.unique_id == "MVEXAMPLE1_accepted_uploads"


async def test_setup_fails_cleanly_when_the_service_is_down(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="mvexample1")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(side_effect=ServiceUnavailable("down")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Retry, not failure: the key is fine, the service is not.
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_a_rejected_key_starts_reauthentication(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="mvexample1")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_entry_can_be_unloaded(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, READY_VIEW)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_grace_sensor_shows_the_margin_before_it_runs_out(hass: HomeAssistant) -> None:
    """The whole point is warning *before* access pauses, not after."""
    view = dict(READY_VIEW)
    view["reciprocity"] = {
        "allowed": True,
        "hoursSilent": 2.5,
        "hoursRemaining": 9.5,
        "everReported": True,
        "graceHours": 12,
    }
    await setup_entry(hass, view)

    state = hass.states.get("sensor.garden_station_extras_remaining")
    assert state.state == "9.5"
    assert state.attributes["derived_data_available"] is True
    assert state.attributes["grace_hours"] == 12


async def test_grace_sensor_reads_zero_once_access_has_paused(hass: HomeAssistant) -> None:
    view = dict(READY_VIEW)
    view["reciprocity"] = {
        "allowed": False,
        "hoursSilent": 13,
        "hoursRemaining": 0,
        "everReported": True,
        "graceHours": 12,
    }
    await setup_entry(hass, view)

    state = hass.states.get("sensor.garden_station_extras_remaining")
    assert state.state == "0.0"
    assert state.attributes["derived_data_available"] is False


async def test_grace_sensor_is_unknown_when_the_service_says_nothing(
    hass: HomeAssistant,
) -> None:
    # An older service version, or a response without the field: report
    # nothing rather than inventing a reassuring zero.
    await setup_entry(hass, READY_VIEW)
    assert hass.states.get("sensor.garden_station_extras_remaining").state == "unknown"
