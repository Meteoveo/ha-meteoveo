"""The Plus surface: the level sensor and the lightning entities (ADR-0866).

Two rules shape all of it:

* An entity that could never have a value is not created. A free account has
  no lightning data, so it gets no lightning entities -- not an entity that
  says "unavailable" forever (ADR-0866 D10.2).
* An entity that *did* exist keeps existing. If the level falls back, the
  entities go unavailable rather than disappearing, so history and
  automations survive the gap (D5).
"""

from __future__ import annotations

import copy

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from conftest import HOME_VIEW
from test_home_entities import ACCOUNT_DATA, STATION_DATA, setup

LEVEL = "sensor.meteoveo_villa_ejemplo_meteoveo_level"
LIGHTNING_NEARBY = "binary_sensor.meteoveo_villa_ejemplo_lightning_nearby"
NEAREST_LIGHTNING = "sensor.meteoveo_villa_ejemplo_nearest_lightning"

LIGHTNING = {
    "locked": False,
    "windowMinutes": 15,
    "nearestKm": 7.4,
    "bearingDeg": 210,
    "count15km": 2,
    "count30km": 5,
    "count50km": 11,
    "lastStrikeAt": "2026-10-23T12:45:00Z",
    "ageMinutes": 5,
    "source": "eumetsat-li",
}


def plus_view(lightning: dict | None = LIGHTNING) -> dict:
    """A home view of an account that has the Plus level."""
    view = copy.deepcopy(HOME_VIEW)
    view["level"] = "plus"
    view["lightning"] = copy.deepcopy(lightning) if lightning is not None else None
    return view


def free_view() -> dict:
    """A home view of a free account: the capability exists, but is locked."""
    view = copy.deepcopy(HOME_VIEW)
    view["level"] = "free"
    view["lightning"] = {"locked": True}
    return view


# --- D3: the level sensor ---------------------------------------------------


async def test_the_level_sensor_reports_free_and_the_locked_lightning(
    hass: HomeAssistant,
) -> None:
    await setup(hass, ACCOUNT_DATA, home=free_view())
    state = hass.states.get(LEVEL)
    assert state is not None
    assert state.state == "free"
    # The attribute is what an automation keys on; it is not translated.
    assert state.attributes["lightning_alerts"] == "locked"
    assert state.attributes["options"] == ["free", "plus"]


async def test_the_level_sensor_reports_plus(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA, home=plus_view())
    state = hass.states.get(LEVEL)
    assert state.state == "plus"
    assert state.attributes["lightning_alerts"] == "available"


async def test_the_level_sensor_is_diagnostic(hass: HomeAssistant) -> None:
    # It is a property of the connection, not a reading: the diagnostics
    # section is where Home Assistant puts such a thing.
    entry = await setup(hass, ACCOUNT_DATA, home=free_view())
    registry = er.async_get(hass)
    assert registry.async_get(LEVEL).entity_category is EntityCategory.DIAGNOSTIC
    assert registry.async_get(LEVEL).unique_id == f"{entry.unique_id}_account_level"


async def test_an_unknown_level_is_unknown_rather_than_free(hass: HomeAssistant) -> None:
    # A response without the field must not be read as "you are free": that
    # would show a paying account as free during a partial outage.
    view = copy.deepcopy(HOME_VIEW)
    view.pop("level")
    await setup(hass, ACCOUNT_DATA, home=view)
    assert hass.states.get(LEVEL).state == "unknown"


# --- D4: no level sensor behind a station key ------------------------------


async def test_a_station_key_entry_gets_no_level_sensor(hass: HomeAssistant) -> None:
    # There is no account behind a station key, so the service always answers
    # "free". A sensor saying so would be a lie, so it is not created.
    await setup(hass, STATION_DATA, home=free_view(), unique_id="mvexample1")
    assert hass.states.get(LEVEL) is None
    assert hass.states.get("sensor.garden_meteoveo_level") is None


# --- D5: the lightning entities are born unlocked --------------------------


async def test_no_lightning_entities_while_the_capability_is_locked(
    hass: HomeAssistant,
) -> None:
    await setup(hass, ACCOUNT_DATA, home=free_view())
    assert hass.states.get(LIGHTNING_NEARBY) is None
    assert hass.states.get(NEAREST_LIGHTNING) is None


async def test_the_lightning_entities_read_the_block(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA, home=plus_view())

    nearby = hass.states.get(LIGHTNING_NEARBY)
    assert nearby.state == "on"
    assert nearby.attributes["nearest_km"] == 7.4
    assert nearby.attributes["bearing_deg"] == 210
    assert nearby.attributes["count_15km"] == 2
    assert nearby.attributes["count_30km"] == 5
    assert nearby.attributes["count_50km"] == 11
    assert nearby.attributes["last_strike_at"] == "2026-10-23T12:45:00Z"
    assert nearby.attributes["window_minutes"] == 15

    nearest = hass.states.get(NEAREST_LIGHTNING)
    assert float(nearest.state) == 7.4
    assert nearest.attributes["unit_of_measurement"] == "km"


async def test_nearby_is_off_when_the_strikes_are_further_than_thirty_km(
    hass: HomeAssistant,
) -> None:
    # The product's own radius for "nearby" is 30 km; a strike at 44 km is
    # data, not an alert.
    far = dict(LIGHTNING, nearestKm=44.0, count15km=0, count30km=0, count50km=3)
    await setup(hass, ACCOUNT_DATA, home=plus_view(far))
    assert hass.states.get(LIGHTNING_NEARBY).state == "off"
    assert float(hass.states.get(NEAREST_LIGHTNING).state) == 44.0


async def test_the_lightning_entities_appear_on_the_first_unlocked_answer(
    hass: HomeAssistant, mock_home_view,
) -> None:
    # Someone who connects a station (or subscribes) while Home Assistant is
    # running should not have to restart it.
    entry = await setup(hass, ACCOUNT_DATA, home=free_view())
    assert hass.states.get(LIGHTNING_NEARBY) is None

    mock_home_view.return_value = (plus_view(), '"e2"')
    await entry.runtime_data.home.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(LIGHTNING_NEARBY).state == "on"


async def test_losing_the_level_makes_them_unavailable_not_gone(
    hass: HomeAssistant, mock_home_view,
) -> None:
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    assert hass.states.get(NEAREST_LIGHTNING) is not None

    mock_home_view.return_value = (free_view(), '"e3"')
    await entry.runtime_data.home.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(LIGHTNING_NEARBY).state == "unavailable"
    assert hass.states.get(NEAREST_LIGHTNING).state == "unavailable"
    # Still registered: the history of the entity is not orphaned.
    registry = er.async_get(hass)
    ids = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert {LIGHTNING_NEARBY, NEAREST_LIGHTNING} <= ids
    assert hass.states.get(LEVEL).attributes["lightning_alerts"] == "locked"


async def test_a_silent_lightning_source_is_unavailable_too(hass: HomeAssistant) -> None:
    # null means "the source is down", not "no lightning anywhere".
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    entry.runtime_data.home.data["lightning"] = None
    entry.runtime_data.home.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(LIGHTNING_NEARBY).state == "unavailable"


async def test_the_entities_come_back_after_a_restart_with_plus(hass: HomeAssistant) -> None:
    # The registry already knows them, so a plus entry recreates them with
    # the same unique ids -- no "_2" duplicates.
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    registry = er.async_get(hass)
    before = registry.async_get(NEAREST_LIGHTNING).unique_id
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(NEAREST_LIGHTNING).unique_id == before
