"""Options -> "Add a weather station" (ADR-0866 D9).

The setup screen's "do you have a weather station?" used to be the only door
to the station, so answering no once meant deleting the integration and
starting again. This is the same door, reachable afterwards.

It has to sign in, because the service does not attach a station to a key it
has already issued -- only create and revoke exist -- so a new integration
key is needed, and issuing one is an account-level action the integration key
itself deliberately cannot do.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoveo.client import ApiError, InvalidCredentials
from custom_components.meteoveo.const import (
    CONF_EMAIL,
    CONF_INTEGRATION_KEY,
    CONF_KEY_ID,
    CONF_MEASUREMENTS,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_REF,
    DOMAIN,
)

from conftest import STATION_VIEW
from test_account_flow import EMAIL, PASSWORD, STATION, TOKEN, Service
from test_account_lifecycle import ACCOUNT_DATA, NEW_KEY, STATION_DATA, add_entry, load


async def open_add_station(hass: HomeAssistant, entry: MockConfigEntry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_station"}
    )


async def test_the_option_is_offered_only_where_it_makes_sense(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["location", "add_station", "delete_account"]

    # An entry that already has a station changes its measurements instead.
    with_station = MockConfigEntry(
        domain=DOMAIN, data={**ACCOUNT_DATA, **STATION_DATA}, unique_id="OTHER"
    )
    with_station.add_to_hass(hass)
    await load(hass, with_station)
    result = await hass.config_entries.options.async_init(with_station.entry_id)
    assert result["menu_options"] == ["location", "measurements", "delete_account"]


async def test_a_station_key_entry_is_not_offered_it(hass: HomeAssistant) -> None:
    # There is no account to create a station on.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key"},
        unique_id="mvexample1",
    )
    entry.add_to_hass(hass)
    await load(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["measurements"]


async def test_adding_a_station_end_to_end(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    assert entry.runtime_data.station is None

    result = await open_add_station(hass, entry)
    assert result["step_id"] == "add_station"
    # The email is offered back; only the password needs typing.
    suggested = {
        str(key): (key.description or {}).get("suggested_value")
        for key in result["data_schema"].schema
    }
    assert suggested["email"] == EMAIL

    with Service(
        async_create_integration_key=AsyncMock(return_value=dict(NEW_KEY))
    ) as service:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        assert result["step_id"] == "station_details"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"station_name": "Huerta", "sensor_height_cm": 180}
        )
        assert result["step_id"] == "measurements"

        with patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], {"temperature": "sensor.outside_temperature"}
            )
            await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The station was created on the account. Home Assistant's own home sits far from
    # the configured place here (the test default), so the entry's place is used rather
    # than moving the station to another province (ADR-0866 D9).
    created = service.async_create_station.await_args.kwargs
    assert created["name"] == "Huerta"
    assert created["sensor_height_cm"] == 180
    assert (created["lat"], created["lon"]) == (38.92, -0.26)

    # A new key, bound to the station; the old one revoked afterwards, so a
    # failure on the way never leaves the entry without a working key.
    issued = service.async_create_integration_key.await_args.kwargs
    assert issued["station_ref"] == STATION["stationId"]
    service.async_delete_integration_key.assert_awaited_once_with(TOKEN, "OLDKEY")

    assert entry.data[CONF_INTEGRATION_KEY] == NEW_KEY["key"]
    assert entry.data[CONF_KEY_ID] == "NEWKEY"
    assert entry.data[CONF_STATION_ID] == STATION["ingestId"]
    assert entry.data[CONF_STATION_KEY] == STATION["secret"]
    assert entry.data[CONF_STATION_REF] == STATION["stationId"]
    assert entry.options[CONF_MEASUREMENTS] == {"temperature": "sensor.outside_temperature"}
    # The connection keeps its identity, so no entity id and no history moves.
    assert entry.unique_id == "OLDKEY"

    # Reloaded with a station: the station entities are there now.
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.station is not None
    assert hass.states.get("sensor.meteoveo_villa_ejemplo_best_forecast_model") is not None


async def test_it_refuses_another_account(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_add_station(hass, entry)
    with Service() as service:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": "otra@example.com", "password": PASSWORD}
        )
    assert result["errors"] == {"email": "wrong_account"}
    service.async_login.assert_not_awaited()


async def test_a_wrong_password_stays_on_the_same_screen(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_add_station(hass, entry)
    with Service(async_login=AsyncMock(side_effect=InvalidCredentials("no"))):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": EMAIL, "password": "wrong"}
        )
    assert result["step_id"] == "add_station"
    assert result["errors"] == {"base": "invalid_login"}
    assert CONF_STATION_ID not in entry.data


async def test_a_full_key_quota_aborts_before_anything_breaks(hass: HomeAssistant) -> None:
    # The old key is still working at this point, so saying so and stopping
    # is better than leaving the entry without one.
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_add_station(hass, entry)
    with Service(
        async_create_integration_key=AsyncMock(side_effect=ApiError(429, "too_many_keys"))
    ) as service:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"station_name": "Huerta", "sensor_height_cm": 180}
        )
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "too_many_keys"
    service.async_delete_integration_key.assert_not_awaited()
    assert entry.data[CONF_INTEGRATION_KEY] == ACCOUNT_DATA[CONF_INTEGRATION_KEY]


async def test_the_station_is_created_once_even_if_the_key_fails(hass: HomeAssistant) -> None:
    # Retrying after a failed key request must not leave a second station on
    # the account.
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_add_station(hass, entry)
    key = AsyncMock(side_effect=[ApiError(500, "oops"), dict(NEW_KEY)])
    with Service(async_create_integration_key=key) as service:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"station_name": "Huerta", "sensor_height_cm": 180}
        )
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
        assert result["step_id"] == "measurements"
        assert result["errors"] == {"base": "unknown"}

        with patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
        ):
            result = await hass.config_entries.options.async_configure(result["flow_id"], {})
            await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert service.async_create_station.await_count == 1


async def test_the_password_is_never_stored(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_add_station(hass, entry)
    with Service(async_create_integration_key=AsyncMock(return_value=dict(NEW_KEY))):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"station_name": "Huerta", "sensor_height_cm": 180}
        )
        with patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
        ):
            await hass.config_entries.options.async_configure(result["flow_id"], {})
            await hass.async_block_till_done()

    stored = f"{entry.data}{entry.options}"
    assert PASSWORD not in stored
    assert TOKEN not in stored

# ADR-0866 D9: a MERT allomas koordinataja nem lehet a kerekitett hely.
#
# A bejegyzes a helyet 0,01 fokra kerekitve tartja (eleg egy elorejelzes-ponthoz), de az
# allomas merese a radar-mero parositasba es a szomszed-logikaba kerul - ott egy kilometer
# nem kozmetika. A telepites 4 tizedest tarol a letett pin-bol; az Options-nal az a pin mar
# nincs meg, ezert a HA SAJAT otthon-koordinatajat hasznaljuk, ha egyezik a hellyel.
def test_the_station_gets_the_precise_home_position_when_it_matches_the_place() -> None:
    from custom_components.meteoveo.config_flow import _station_place

    class _Hass:
        class config:  # noqa: N801 - a HA `hass.config`-ja ilyen alakú
            latitude = 38.9249
            longitude = -0.2551

    # A hely (38.92, -0.26) a kerekitett valtozata ugyanennek: a pontos ertek jon.
    assert _station_place(_Hass(), 38.92, -0.26) == (38.9249, -0.2551)


def test_a_distant_home_does_not_move_the_station() -> None:
    from custom_components.meteoveo.config_flow import _station_place

    class _Hass:
        class config:  # noqa: N801
            latitude = 32.87336  # a HA alapertelmezese (San Diego)
            longitude = -117.22743

    # Tul messze: a bejegyzes helye marad, mert nem tudjuk, hol all az allomas.
    assert _station_place(_Hass(), 38.92, -0.26) == (38.92, -0.26)


def test_a_home_without_coordinates_falls_back_to_the_place() -> None:
    from custom_components.meteoveo.config_flow import _station_place

    class _Hass:
        class config:  # noqa: N801
            latitude = None
            longitude = None

    assert _station_place(_Hass(), 38.92, -0.26) == (38.92, -0.26)


async def test_adding_a_station_uses_the_home_position(hass: HomeAssistant) -> None:
    """Vegig a folyamaton: a HA otthona a helyen van -> a pontos koordinata megy fel."""
    await hass.config.async_update(latitude=38.9249, longitude=-0.2551)
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)

    result = await open_add_station(hass, entry)
    with Service(async_create_integration_key=AsyncMock(return_value=dict(NEW_KEY))) as service:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"station_name": "Huerta", "sensor_height_cm": 180}
        )
        with patch(
            "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
            new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
        ):
            await hass.config_entries.options.async_configure(
                result["flow_id"], {"temperature": "sensor.outside_temperature"}
            )
            await hass.async_block_till_done()

    created = service.async_create_station.await_args.kwargs
    assert (created["lat"], created["lon"]) == (38.9249, -0.2551)
