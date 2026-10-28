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


async def _set_up_uploading_entry(hass):
    """An entry with one mapped measurement, its station view patched to load."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    return entry


_VIEW = {"station": {"name": "Garden"}, "health": {"findings": []},
         "model": {"status": "collecting", "samples": 0, "samplesNeeded": 10,
                   "daysRemaining": 10},
         "upload": {"lastSeenAt": None, "acceptedCount": 0, "lastError": None}}


async def test_a_rejected_key_during_upload_asks_for_a_new_one(hass) -> None:
    """The timer is not the coordinator: the rejection has to start reauth itself."""
    from datetime import timedelta
    from unittest.mock import AsyncMock, patch

    from homeassistant.config_entries import SOURCE_REAUTH
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.meteoveo.client import InvalidCredentials

    entry = await _set_up_uploading_entry(hass)
    with (
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=_VIEW),
        ),
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_upload",
            new=AsyncMock(side_effect=InvalidCredentials("station id or key was rejected")),
        ) as upload,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Two ticks: a key that stays rejected must not stack up prompts.
        for minutes in (1, 2):
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61 * minutes))
            await hass.async_block_till_done()

    assert upload.await_count == 2
    assert len(list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))) == 1


async def test_an_unreachable_service_during_upload_is_not_an_error(hass, caplog) -> None:
    """A lost connection waits for the next tick; it must not log an error every minute."""
    import logging
    from datetime import timedelta
    from unittest.mock import AsyncMock, patch

    import aiohttp
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    attempts = []

    class Unreachable:
        async def __aenter__(self):
            raise aiohttp.ClientConnectionError("connection refused")

        async def __aexit__(self, *exc):
            return False

    class Session:
        def get(self, url, **kwargs):
            attempts.append(url)
            return Unreachable()

    entry = await _set_up_uploading_entry(hass)
    with (
        patch("custom_components.meteoveo.async_get_clientsession", return_value=Session()),
        patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=_VIEW),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()

    assert attempts, "the upload was never attempted, so the test proves nothing"
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


async def test_the_timer_sends_a_reduced_reading_in_its_own_field(hass) -> None:
    """MeteoVeo ADR-0844, end to end: the stored answer reaches the request.

    A console that already reduces to sea level must not have its value land
    in the absolute field -- the server would reduce it a second time, about
    0.12 hPa per metre.
    """
    from datetime import timedelta
    from unittest.mock import AsyncMock, patch

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

    from custom_components.meteoveo.const import (
        CONF_MEASUREMENTS,
        CONF_PRESSURE_KIND,
        CONF_STATION_ID,
        CONF_STATION_KEY,
        DOMAIN,
    )
    from custom_components.meteoveo.wu_payload import PRESSURE_SEA_LEVEL

    hass.states.async_set("sensor.barometer", "1013.25", {"unit_of_measurement": "hPa"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key"},
        unique_id="mvexample1",
        options={
            CONF_MEASUREMENTS: {"pressure": "sensor.barometer"},
            CONF_PRESSURE_KIND: PRESSURE_SEA_LEVEL,
        },
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

    fields = upload.await_args.args[0]
    assert "absbaromin" not in fields
    assert fields["baromin"] == 29.9213
