"""The official warning by phenomenon (ADR-0935).

Until 0.3.4 the phenomenon of a warning was only *data* -- a key in an
attribute list. These tests pin the automatable surface: one binary sensor per
phenomenon that has actually occurred at the place, a second event entity
whose event type is the phenomenon, and the rule that a missing warnings block
never reads as "no danger".

The helpers are pure and tested directly; the entities through a real config
entry at a frozen time, against the example home view in conftest.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.meteoveo import home
from conftest import HOME_VIEW
from test_home_entities import ACCOUNT_DATA, setup

NOW = datetime(2026, 10, 23, 13, 5, tzinfo=timezone.utc)
DURING = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)
BASE = "meteoveo_villa_ejemplo"

#: The AEMET Meteoalerta codes, as the service's own table has them
#: (services/api/src/forecast/warning-sentence.ts, PHENOMENON / WARNING_CODES).
#: Written out here so a drift on either side fails a test rather than quietly
#: dropping a phenomenon on the floor.
CANONICAL = ("PR", "TO", "VI", "NE", "CA", "BF", "CO", "NI", "DP", "AL", "PO")

WIND_WARNING = {
    "level": "orange",
    "phenomenon": "VI",
    "phenomenonName": "Vientos",
    "probability": "40%-70%",
    "headline": "Aviso naranja por vientos",
    "onset": "2026-10-23T18:00:00Z",
    "expires": "2026-10-24T06:00:00Z",
}


# --- pure helpers ------------------------------------------------------------


def test_the_phenomenon_list_is_the_aemet_meteoalerta_one() -> None:
    assert home.WARNING_PHENOMENA == CANONICAL


def test_the_warning_carries_the_aemet_probability_band() -> None:
    # The service sends it; until now we dropped it, so neither the attribute
    # nor the event body had it. Verbatim -- we compute nothing from it.
    (warning,) = home.warnings_list(HOME_VIEW)
    assert warning["probability"] == "40%-70%"
    assert warning["phenomenon"] == "PR"


def test_announced_phenomena_count_before_the_warning_starts() -> None:
    # The entity has to exist from the announcement, not from the onset: an
    # automation is built in the hours before the storm, not during it.
    assert home.warned_phenomena(HOME_VIEW) == {"PR"}
    view = copy.deepcopy(HOME_VIEW)
    view["warnings"].append(WIND_WARNING)
    assert home.warned_phenomena(view) == {"PR", "VI"}


def test_an_unknown_phenomenon_code_is_not_invented_into_an_entity() -> None:
    view = copy.deepcopy(HOME_VIEW)
    view["warnings"][0]["phenomenon"] = "ZZ"
    assert home.warned_phenomena(view) == set()


def test_without_a_warnings_block_no_phenomenon_is_claimed() -> None:
    view = copy.deepcopy(HOME_VIEW)
    del view["warnings"]
    assert home.warnings_list(view) is None
    assert home.warned_phenomena(view) == set()
    assert home.active_phenomena(None, NOW) == set()


def test_active_phenomena_are_the_ones_in_force_now() -> None:
    warnings = home.warnings_list(HOME_VIEW)
    assert home.active_phenomena(warnings, NOW) == set()  # starts at 15:00
    assert home.active_phenomena(warnings, DURING) == {"PR"}


def test_the_highest_level_of_a_phenomenon_is_a_choice_not_a_calculation() -> None:
    # Two AEMET warnings for the same phenomenon: we pick the one AEMET itself
    # called the worst. We never derive a level of our own.
    warnings = [
        {"level": "yellow", "phenomenon": "VI", "onset": "2026-10-23T12:00:00Z",
         "expires": "2026-10-23T23:00:00Z"},
        {"level": "orange", "phenomenon": "VI", "onset": "2026-10-23T12:00:00Z",
         "expires": "2026-10-23T23:00:00Z"},
    ]
    assert home.highest_level(home.phenomenon_warnings(warnings, "VI", DURING)) == "orange"
    assert home.phenomenon_warnings(warnings, "PR", DURING) == []


# --- entities ---------------------------------------------------------------


async def test_the_phenomenon_sensor_exists_for_the_warned_phenomenon_only(
    hass: HomeAssistant, freezer
) -> None:
    freezer.move_to(NOW)
    entry = await setup(hass, ACCOUNT_DATA)
    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    # The example view carries a rain warning and nothing else.
    assert f"binary_sensor.{BASE}_rain_warning" in ids
    for absent in ("thunderstorm", "wind", "avalanche", "snowmelt"):
        assert f"binary_sensor.{BASE}_{absent}_warning" not in ids, absent


async def test_the_phenomenon_sensor_is_off_before_and_on_during(
    hass: HomeAssistant, freezer
) -> None:
    freezer.move_to(NOW)
    await setup(hass, ACCOUNT_DATA)
    assert hass.states.get(f"binary_sensor.{BASE}_rain_warning").state == "off"


async def test_the_phenomenon_sensor_turns_on_and_quotes_aemet(
    hass: HomeAssistant, freezer
) -> None:
    freezer.move_to(DURING)
    await setup(hass, ACCOUNT_DATA)
    state = hass.states.get(f"binary_sensor.{BASE}_rain_warning")
    assert state.state == "on"
    assert state.attributes["phenomenon"] == "PR"
    assert state.attributes["phenomenon_name"] == "Lluvias"
    assert state.attributes["highest_level"] == "yellow"
    assert state.attributes["warnings"][0]["headline"] == "Aviso amarillo por lluvias"
    assert state.attributes["warnings"][0]["probability"] == "40%-70%"
    assert state.attributes["device_class"] == "safety"


async def test_a_new_phenomenon_gets_its_sensor_on_the_next_refresh(
    hass: HomeAssistant, freezer
) -> None:
    freezer.move_to(NOW)
    entry = await setup(hass, ACCOUNT_DATA)
    wind = f"binary_sensor.{BASE}_wind_warning"
    assert hass.states.get(wind) is None

    view = copy.deepcopy(HOME_VIEW)
    view["warnings"].append(WIND_WARNING)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(view, '"e2"')),
    ):
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get(wind)
    # Announced but not yet started: the entity exists and says "not in force".
    assert state is not None and state.state == "off"
    assert state.attributes["warnings"] == []


async def test_a_phenomenon_sensor_once_created_stays(hass: HomeAssistant, freezer) -> None:
    # An entity that vanished when the storm passed would take the automation
    # pointing at it with it (the ADR-0866 D10.2 rule, applied here).
    freezer.move_to(NOW)
    view = copy.deepcopy(HOME_VIEW)
    view["warnings"] = []
    entry = await setup(hass, ACCOUNT_DATA, home=copy.deepcopy(HOME_VIEW))
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(view, '"e2"')),
    ):
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(f"binary_sensor.{BASE}_rain_warning").state == "off"


async def test_without_a_warnings_block_nothing_says_no_danger(
    hass: HomeAssistant, freezer
) -> None:
    """The heart of it: a missing block is not a statement (AGENTS.md)."""
    freezer.move_to(NOW)
    view = copy.deepcopy(HOME_VIEW)
    del view["warnings"]
    await setup(hass, ACCOUNT_DATA, home=view)

    # No phenomenon entity is invented out of silence.
    assert hass.states.get(f"binary_sensor.{BASE}_rain_warning") is None
    # Every level sensor is unknown, not "off".
    for level in ("yellow", "orange", "red"):
        assert hass.states.get(f"binary_sensor.{BASE}_{level}_warning").state == "unknown"
    # And the count sensor's attributes do not fill the silence with "none".
    warnings = hass.states.get(f"sensor.{BASE}_weather_warnings")
    assert warnings.state == "unknown"
    assert warnings.attributes["highest_level"] is None
    assert warnings.attributes["warnings"] is None


async def test_an_empty_warnings_list_is_a_real_statement(
    hass: HomeAssistant, freezer
) -> None:
    # AEMET saying "there are none" is knowledge, and must read as "off".
    freezer.move_to(NOW)
    view = copy.deepcopy(HOME_VIEW)
    view["warnings"] = []
    await setup(hass, ACCOUNT_DATA, home=view)
    for level in ("yellow", "orange", "red"):
        assert hass.states.get(f"binary_sensor.{BASE}_{level}_warning").state == "off"
    warnings = hass.states.get(f"sensor.{BASE}_weather_warnings")
    assert warnings.state == "0"
    assert warnings.attributes["highest_level"] == "none"


# --- the second event entity -------------------------------------------------


async def test_the_phenomenon_event_declares_every_aemet_code(
    hass: HomeAssistant, freezer
) -> None:
    freezer.move_to(NOW)
    await setup(hass, ACCOUNT_DATA)
    state = hass.states.get(f"event.{BASE}_new_warning_by_phenomenon")
    assert state is not None
    assert state.attributes["event_types"] == [c.lower() for c in CANONICAL] + ["other"]
    # Warnings already known at start-up do not fire (a restart must not
    # re-notify), exactly as for the level event.
    assert state.state == "unknown"


async def test_the_phenomenon_event_fires_with_the_code_and_the_level(
    hass: HomeAssistant, freezer
) -> None:
    freezer.move_to(NOW)
    entry = await setup(hass, ACCOUNT_DATA)
    event_id = f"event.{BASE}_new_warning_by_phenomenon"

    view = copy.deepcopy(HOME_VIEW)
    view["warnings"].append(WIND_WARNING)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(view, '"e2"')),
    ):
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get(event_id)
    assert state.attributes["event_type"] == "vi"
    assert state.attributes["phenomenon"] == "VI"
    assert state.attributes["level"] == "orange"
    assert state.attributes["phenomenon_name"] == "Vientos"
    assert state.attributes["probability"] == "40%-70%"
    assert state.attributes["headline"] == "Aviso naranja por vientos"
    assert state.attributes["onset"] == "2026-10-23T18:00:00Z"
    assert state.attributes["expires"] == "2026-10-24T06:00:00Z"
    fired_at = state.state

    # The same warning again does not fire again.
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(copy.deepcopy(view), '"e3"')),
    ):
        freezer.tick(300)
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(event_id).state == fired_at


async def test_an_unknown_code_fires_as_other_and_keeps_the_raw_code(
    hass: HomeAssistant, freezer
) -> None:
    # We do not guess what a code we have never seen means, and we do not
    # swallow the warning either.
    freezer.move_to(NOW)
    entry = await setup(hass, ACCOUNT_DATA)
    view = copy.deepcopy(HOME_VIEW)
    view["warnings"].append({**WIND_WARNING, "phenomenon": "ZZ", "phenomenonName": "Algo nuevo"})
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(view, '"e2"')),
    ):
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get(f"event.{BASE}_new_warning_by_phenomenon")
    assert state.attributes["event_type"] == "other"
    assert state.attributes["phenomenon"] == "ZZ"
    assert state.attributes["phenomenon_name"] == "Algo nuevo"
    # No binary sensor was invented for it.
    assert hass.states.get(f"binary_sensor.{BASE}_zz_warning") is None


async def test_the_level_event_body_gained_level_and_probability(
    hass: HomeAssistant, freezer
) -> None:
    # Additive: the five keys it had are unchanged, so an automation built on
    # 0.3.x keeps working.
    freezer.move_to(NOW)
    entry = await setup(hass, ACCOUNT_DATA)
    view = copy.deepcopy(HOME_VIEW)
    view["warnings"].append(WIND_WARNING)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_home",
        new=AsyncMock(return_value=(view, '"e2"')),
    ):
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get(f"event.{BASE}_new_warning")
    assert state.attributes["event_type"] == "orange"
    assert state.attributes["headline"] == "Aviso naranja por vientos"
    assert state.attributes["phenomenon"] == "VI"
    assert state.attributes["phenomenon_name"] == "Vientos"
    assert state.attributes["onset"] == "2026-10-23T18:00:00Z"
    assert state.attributes["expires"] == "2026-10-24T06:00:00Z"
    assert state.attributes["level"] == "orange"
    assert state.attributes["probability"] == "40%-70%"
