"""Forecast entities (0.2.0): weather, rain in the next hour, warnings.

Exercised through a real config entry, for an account entry without a
station, an account entry with one, and a 0.1.x station-key entry.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

from homeassistant.components.weather import (
    DOMAIN as WEATHER_DOMAIN,
    SERVICE_GET_FORECASTS,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoveo.client import InvalidCredentials, ServiceUnavailable
from custom_components.meteoveo.const import (
    CONF_EMAIL,
    CONF_INTEGRATION_KEY,
    CONF_KEY_ID,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_REF,
    DOMAIN,
)

from conftest import HOME_VIEW, STATION_VIEW

ACCOUNT_DATA = {
    CONF_INTEGRATION_KEY: "mvik_EXAMPLEKEY.example-secret",
    CONF_KEY_ID: "EXAMPLEKEY",
    CONF_EMAIL: "ana@example.com",
    "latitude": 38.92,
    "longitude": -0.26,
}
STATION_DATA = {
    CONF_STATION_ID: "MVEXAMPLE1",
    CONF_STATION_KEY: "station-secret",
    CONF_STATION_REF: 123,
}

WEATHER = "weather.villa_ejemplo"
RAIN_SOON = "binary_sensor.villa_ejemplo_rain_in_the_next_hour"
RAIN_START = "sensor.villa_ejemplo_rain_start"
RAIN_END = "sensor.villa_ejemplo_rain_end"
WARNINGS = "sensor.villa_ejemplo_weather_warnings"


async def setup(hass: HomeAssistant, data: dict, home=None, unique_id="EXAMPLEKEY"):
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, unique_id=unique_id, title="Villa Ejemplo"
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(home or copy.deepcopy(HOME_VIEW), '"e"')),
    ), patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_account_entry_without_station_gets_the_forecast_only(
    hass: HomeAssistant,
) -> None:
    entry = await setup(hass, ACCOUNT_DATA)
    assert entry.state is ConfigEntryState.LOADED

    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert ids == {WEATHER, RAIN_SOON, RAIN_START, RAIN_END, WARNINGS}

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "EXAMPLEKEY")})
    assert device.name == "Villa Ejemplo"


async def test_translation_keys_are_the_ones_the_card_relies_on(hass: HomeAssistant) -> None:
    entry = await setup(hass, ACCOUNT_DATA)
    registry = er.async_get(hass)
    keys = {
        e.entity_id: e.translation_key
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert keys == {
        WEATHER: "forecast",
        RAIN_SOON: "rain_soon",
        RAIN_START: "rain_start",
        RAIN_END: "rain_end",
        WARNINGS: "warnings",
    }


async def test_weather_now(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA)
    state = hass.states.get(WEATHER)
    assert state.state == "partlycloudy"
    assert state.attributes["temperature"] == 23.1
    assert state.attributes["humidity"] == 44
    # m/s -> km/h is Home Assistant's job, from the declared native unit.
    assert state.attributes["wind_speed"] == round(2.6 * 3.6, 2)
    assert state.attributes["wind_bearing"] == 113
    assert "pressure" not in state.attributes or state.attributes["pressure"] is None
    assert state.attributes["attribution"] == "Datos: © AEMET, MeteoVeo."


async def _forecasts(hass: HomeAssistant, kind: str) -> list[dict]:
    response = await hass.services.async_call(
        WEATHER_DOMAIN,
        SERVICE_GET_FORECASTS,
        {"entity_id": WEATHER, "type": kind},
        blocking=True,
        return_response=True,
    )
    return response[WEATHER]["forecast"]


async def test_hourly_forecast(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA)
    hourly = await _forecasts(hass, "hourly")
    assert len(hourly) == 2
    first, night = hourly
    assert first["condition"] == "partlycloudy"
    assert first["temperature"] == 23.0
    assert first["precipitation_probability"] == 0
    assert first["is_daytime"] is True
    assert night["is_daytime"] is False
    # Unknown stays unknown: not zero.
    assert "apparent_temperature" not in night
    assert "precipitation" not in night


async def test_daily_forecast_leaves_out_trend_days(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA)
    daily = await _forecasts(hass, "daily")
    assert len(daily) == 1
    assert daily[0]["temperature"] == 24
    assert daily[0]["templow"] == 13
    assert daily[0]["datetime"].startswith("2026-10-23")


async def test_rain_soon(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA)
    state = hass.states.get(RAIN_SOON)
    assert state.state == "on"
    assert state.attributes["rain_now"] is False
    assert state.attributes["starts_at"] == "2026-10-23T13:20:00Z"
    assert state.attributes["ends_at"] is None
    assert state.attributes["issued_at"] == "2026-10-23T12:48:00Z"
    # Counted from issued_at at update time (a reused 304 reply must not freeze it).
    assert isinstance(state.attributes["age_minutes"], int)
    assert state.attributes["age_minutes"] >= 0
    assert state.attributes["steps"][1] == {
        "at": "2026-10-23T13:20:00Z",
        "lead_minutes": 30,
        "band": "light",
        "source": "model",
        "uncertain": True,
    }

    assert hass.states.get(RAIN_START).state == "2026-10-23T13:20:00+00:00"
    assert hass.states.get(RAIN_END).state == "unknown"


async def test_outside_nowcast_coverage_the_rain_entities_are_unavailable(
    hass: HomeAssistant,
) -> None:
    home = copy.deepcopy(HOME_VIEW)
    home["nextHour"] = None
    await setup(hass, ACCOUNT_DATA, home=home)
    for entity_id in (RAIN_SOON, RAIN_START, RAIN_END):
        assert hass.states.get(entity_id).state == "unavailable", entity_id
    # The forecast itself is unaffected.
    assert hass.states.get(WEATHER).state == "partlycloudy"


async def test_warnings(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA)
    state = hass.states.get(WARNINGS)
    assert state.state == "1"
    assert state.attributes["highest_level"] == "yellow"
    assert state.attributes["warnings"] == [
        {
            "level": "yellow",
            "phenomenon": "PR",
            "phenomenon_name": "Lluvias",
            "headline": "Aviso amarillo por lluvias",
            "onset": "2026-10-23T15:00:00Z",
            "expires": "2026-10-23T23:59:00Z",
        }
    ]


async def test_no_warnings(hass: HomeAssistant) -> None:
    home = copy.deepcopy(HOME_VIEW)
    home["warnings"] = []
    await setup(hass, ACCOUNT_DATA, home=home)
    state = hass.states.get(WARNINGS)
    assert state.state == "0"
    assert state.attributes["highest_level"] == "none"


async def test_account_entry_with_station_has_both_sets(hass: HomeAssistant) -> None:
    entry = await setup(hass, {**ACCOUNT_DATA, **STATION_DATA})
    registry = er.async_get(hass)
    ids = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert WEATHER in ids
    assert "sensor.villa_ejemplo_best_forecast_model" in ids
    assert "binary_sensor.villa_ejemplo_sensor_problem" in ids
    # One device, named after the place -- not the station.
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [d.name for d in devices] == ["Villa Ejemplo"]


async def test_station_key_entry_gets_the_forecast_too(hass: HomeAssistant) -> None:
    entry = await setup(
        hass,
        {CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "k"},
        unique_id="mvexample1",
    )
    assert entry.state is ConfigEntryState.LOADED
    # 0.1.x entities keep their ids; the forecast joins the station's device.
    assert hass.states.get("weather.garden").state == "partlycloudy"
    assert hass.states.get("binary_sensor.garden_rain_in_the_next_hour").state == "on"
    entity = er.async_get(hass).async_get("weather.garden")
    assert entity.unique_id == "MVEXAMPLE1_forecast"


async def test_a_rejected_integration_key_starts_reauthentication(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ACCOUNT_DATA, unique_id="EXAMPLEKEY")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_forecast_outage_retries_setup(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=ACCOUNT_DATA, unique_id="EXAMPLEKEY")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(side_effect=ServiceUnavailable("down")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_a_forecast_outage_does_not_stop_a_station(hass: HomeAssistant) -> None:
    # Station-key entry: the station view decides; the forecast may be down.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "k"},
        unique_id="mvexample1",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ), patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("weather.garden").state == "unavailable"
    assert not any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_not_modified_keeps_the_previous_view(hass: HomeAssistant) -> None:
    entry = await setup(hass, ACCOUNT_DATA)
    coordinator = entry.runtime_data.home
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(None, '"e"')),
    ) as mocked:
        await coordinator.async_refresh()
    assert mocked.await_args.kwargs["etag"] == '"e"'
    assert coordinator.last_update_success
    assert hass.states.get(WEATHER).state == "partlycloudy"


async def test_best_model_paused_while_the_station_is_silent(hass: HomeAssistant) -> None:
    view = copy.deepcopy(STATION_VIEW)
    view["model"] = {"status": "paused", "hoursSilent": 30, "graceHours": 12}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "k"},
        unique_id="mvexample1",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=view),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    state = hass.states.get("sensor.garden_best_forecast_model")
    assert state.state == "paused"
    assert state.attributes["hours_silent"] == 30
    assert state.attributes["grace_hours"] == 12


async def test_rain_soon_age_counts_from_issued_at(hass: HomeAssistant, freezer) -> None:
    """The age is counted from issued_at, not copied from the reply."""
    freezer.move_to("2026-10-23T13:05:30Z")
    await setup(hass, ACCOUNT_DATA)
    # issuedAt 12:48:00 -> 17 minutes, although the reply said 2.
    assert hass.states.get(RAIN_SOON).attributes["age_minutes"] == 17
