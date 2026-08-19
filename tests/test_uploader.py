"""Reading Home Assistant states and turning them into an upload."""

from __future__ import annotations

import pytest

from custom_components.meteoveo.uploader import collect_readings


class FakeState:
    def __init__(self, state, unit=None):
        self.state = state
        self.attributes = {"unit_of_measurement": unit} if unit else {}


class FakeStates:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        return self._mapping.get(entity_id)


def test_reads_the_mapped_entities():
    states = FakeStates(
        {
            "sensor.t": FakeState("21.37", "°C"),
            "sensor.h": FakeState("58", "%"),
        }
    )
    readings = collect_readings(states, {"temperature": "sensor.t", "humidity": "sensor.h"})

    assert readings == {"temperature": ("21.37", "°C"), "humidity": ("58", "%")}


def test_a_missing_entity_is_skipped_not_guessed():
    # The entity may have been renamed or removed after setup.
    states = FakeStates({"sensor.t": FakeState("21.37", "°C")})
    readings = collect_readings(states, {"temperature": "sensor.t", "humidity": "sensor.gone"})

    assert "humidity" not in readings
    assert "temperature" in readings


def test_an_entity_without_a_unit_is_still_read():
    # Wind direction commonly has no unit; the catalogue decides what to do.
    states = FakeStates({"sensor.d": FakeState("270")})
    readings = collect_readings(states, {"wind_direction": "sensor.d"})

    assert readings == {"wind_direction": ("270", "")}


@pytest.mark.parametrize("bad", ["unknown", "unavailable"])
def test_unusable_states_are_passed_through_for_the_payload_to_reject(bad):
    # collect_readings does not judge values -- one place decides what is
    # usable, and that place is the payload builder.
    states = FakeStates({"sensor.t": FakeState(bad, "°C")})
    assert collect_readings(states, {"temperature": "sensor.t"}) == {"temperature": (bad, "°C")}


def test_nothing_mapped_means_nothing_to_read():
    assert collect_readings(FakeStates({}), {}) == {}


def test_one_entity_can_feed_two_measurements():
    states = FakeStates({"sensor.w": FakeState("4.5", "m/s")})
    readings = collect_readings(states, {"wind_speed": "sensor.w", "wind_gust": "sensor.w"})

    assert readings["wind_speed"] == readings["wind_gust"] == ("4.5", "m/s")


async def test_the_timer_uploads_the_mapped_reading(hass) -> None:
    """End to end through Home Assistant: a mapped entity reaches the service."""
    from datetime import timedelta
    from unittest.mock import AsyncMock, patch

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

    from custom_components.meteoveo.const import (
        CONF_MEASUREMENTS,
        CONF_STATION_ID,
        CONF_STATION_KEY,
        DOMAIN,
    )

    hass.states.async_set("sensor.outside", "21.37", {"unit_of_measurement": "°C"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key"},
        unique_id="mvexample1",
        options={CONF_MEASUREMENTS: {"temperature": "sensor.outside"}},
    )
    entry.add_to_hass(hass)

    view = {"station": {"name": "Garden"}, "health": {"findings": []},
            "model": {"status": "collecting", "samples": 0, "samplesNeeded": 10,
                      "daysRemaining": 10},
            "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None}}

    with (
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=view),
        ),
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_upload",
            new=AsyncMock(return_value=True),
        ) as upload,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()

    upload.assert_awaited()
    fields = upload.await_args.args[0]
    # 21.37 C is 70.47 F -- converted, not passed through.
    assert fields["tempf"] == 70.47


async def test_nothing_mapped_means_no_request(hass) -> None:
    from datetime import timedelta
    from unittest.mock import AsyncMock, patch

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

    from custom_components.meteoveo.const import CONF_STATION_ID, CONF_STATION_KEY, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key"},
        unique_id="mvexample1",
        options={},
    )
    entry.add_to_hass(hass)

    view = {"station": {"name": "Garden"}, "health": {"findings": []},
            "model": {"status": "collecting", "samples": 0, "samplesNeeded": 10,
                      "daysRemaining": 10},
            "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None}}

    with (
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=view),
        ),
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_upload",
            new=AsyncMock(return_value=True),
        ) as upload,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()

    upload.assert_not_awaited()
