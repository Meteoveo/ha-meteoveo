"""More from the home view (0.2.0, ADR-0827 B1/B2): derived sensors, warnings by level.

The helpers are pure and tested directly; the entities through a real config
entry at a frozen time, against the example home view in conftest.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.meteoveo import home
from conftest import HOME_VIEW
from test_home_entities import ACCOUNT_DATA, setup

NOW = datetime(2026, 10, 23, 13, 5, tzinfo=timezone.utc)
BASE = "meteoveo_villa_ejemplo"


# --- pure helpers ------------------------------------------------------------


def test_dew_point_from_temperature_and_humidity() -> None:
    assert home.dew_point(23.1, 44) == 10.2
    assert home.dew_point(10.0, 100) == 10.0
    assert home.dew_point(None, 44) is None
    assert home.dew_point(23.1, None) is None
    assert home.dew_point(23.1, 0) is None


def test_current_hour_is_the_one_containing_now() -> None:
    hour = home.current_hour(HOME_VIEW, NOW)
    assert hour is not None and hour["at"] == "2026-10-23T13:00:00Z"
    # Before the first hour: nothing to pretend with.
    assert home.current_hour(HOME_VIEW, datetime(2026, 10, 23, 11, 0, tzinfo=timezone.utc)) is None


def test_minutes_to_rain() -> None:
    next_hour = HOME_VIEW["nextHour"]
    assert home.minutes_to_rain(next_hour, NOW) == 15
    assert home.minutes_to_rain({**next_hour, "rainNow": True}, NOW) == 0
    assert home.minutes_to_rain({**next_hour, "rainStartsAt": None}, NOW) is None
    # A start already passed but not marked as "now" counts as now, never negative.
    late = datetime(2026, 10, 23, 13, 30, tzinfo=timezone.utc)
    assert home.minutes_to_rain(next_hour, late) == 0


def test_rain_intensity_is_the_step_covering_now() -> None:
    next_hour = HOME_VIEW["nextHour"]
    assert home.rain_intensity_now(next_hour, NOW) == "none"
    assert home.rain_intensity_now(next_hour, datetime(2026, 10, 23, 13, 25, tzinfo=timezone.utc)) == "light"
    assert home.rain_intensity_now({"steps": []}, NOW) is None


def test_warnings_active_and_next() -> None:
    warnings = home.warnings_list(HOME_VIEW)
    assert home.active_levels(warnings, NOW) == set()
    assert home.next_warning_onset(warnings, NOW) == datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
    during = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)
    assert home.active_levels(warnings, during) == {"yellow"}
    assert home.next_warning_onset(warnings, during) is None


def test_warning_identity_is_phenomenon_level_and_onset() -> None:
    (warning,) = home.warnings_list(HOME_VIEW)
    assert home.warning_id(warning) == "PR|yellow|2026-10-23T15:00:00Z"


# --- entities ----------------------------------------------------------------


async def test_derived_sensors(hass: HomeAssistant, freezer) -> None:
    freezer.move_to(NOW)
    await setup(hass, ACCOUNT_DATA)

    assert hass.states.get(f"sensor.{BASE}_feels_like").state == "23"
    assert hass.states.get(f"sensor.{BASE}_dew_point").state == "10.2"
    assert hass.states.get(f"sensor.{BASE}_uv_index").state == "3"
    assert hass.states.get(f"sensor.{BASE}_uv_index_today_max").state == "3"
    assert hass.states.get(f"sensor.{BASE}_minutes_until_rain").state == "15"
    assert hass.states.get(f"sensor.{BASE}_rain_intensity_now").state == "none"

    weather = hass.states.get(f"weather.{BASE}")
    assert weather.attributes["apparent_temperature"] == 23
    assert weather.attributes["dew_point"] == 10.2
    assert weather.attributes["uv_index"] == 3


async def test_minutes_until_rain_is_unknown_without_rain(hass: HomeAssistant, freezer) -> None:
    freezer.move_to(NOW)
    view = copy.deepcopy(HOME_VIEW)
    view["nextHour"]["rainSoon"] = False
    view["nextHour"]["rainStartsAt"] = None
    await setup(hass, ACCOUNT_DATA, home=view)
    assert hass.states.get(f"sensor.{BASE}_minutes_until_rain").state == "unknown"


async def test_warnings_by_level(hass: HomeAssistant, freezer) -> None:
    freezer.move_to(NOW)
    await setup(hass, ACCOUNT_DATA)
    assert hass.states.get(f"binary_sensor.{BASE}_yellow_warning").state == "off"
    assert hass.states.get(f"binary_sensor.{BASE}_orange_warning").state == "off"
    assert hass.states.get(f"binary_sensor.{BASE}_red_warning").state == "off"
    assert hass.states.get(f"sensor.{BASE}_next_warning").state == "2026-10-23T15:00:00+00:00"


async def test_warning_level_turns_on_during_the_warning(hass: HomeAssistant, freezer) -> None:
    freezer.move_to(datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc))
    await setup(hass, ACCOUNT_DATA)
    state = hass.states.get(f"binary_sensor.{BASE}_yellow_warning")
    assert state.state == "on"
    assert state.attributes["warnings"][0]["headline"] == "Aviso amarillo por lluvias"
    assert hass.states.get(f"sensor.{BASE}_next_warning").state == "unknown"


async def test_new_warning_fires_an_event_once(hass: HomeAssistant, freezer) -> None:
    freezer.move_to(NOW)
    entry = await setup(hass, ACCOUNT_DATA)
    event_id = f"event.{BASE}_new_warning"
    # Warnings already there at start-up do not fire (a restart must not re-notify).
    assert hass.states.get(event_id).state == "unknown"

    view = copy.deepcopy(HOME_VIEW)
    view["warnings"].append(
        {"level": "orange", "phenomenon": "VI", "phenomenonName": "Vientos",
         "probability": "40%-70%", "headline": "Aviso naranja por vientos",
         "onset": "2026-10-23T18:00:00Z", "expires": "2026-10-24T06:00:00Z"}
    )
    coordinator = entry.runtime_data.home
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(view, '"e2"')),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get(event_id)
    assert state.attributes["event_type"] == "orange"
    assert state.attributes["headline"] == "Aviso naranja por vientos"
    fired_at = state.state

    # The same warning on the next refresh does not fire again.
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(copy.deepcopy(view), '"e3"')),
    ):
        freezer.tick(300)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(event_id).state == fired_at
