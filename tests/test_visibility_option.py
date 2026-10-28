"""Options -> "Public visibility" (MeteoVeo ADR-0872).

The same switch exists on the website, so the form must read the CURRENT state
from the service: a copy kept in the entry would quietly undo a change made
there. Writing goes out with the station token -- the integration never holds
an account token (ADR-0827).
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoveo.client import InvalidCredentials, ServiceUnavailable
from custom_components.meteoveo.const import DOMAIN

from conftest import STATION_VIEW
from test_account_lifecycle import ACCOUNT_DATA, STATION_DATA, add_entry, load

SELF_OFF = {**copy.deepcopy(STATION_VIEW), "publicDisplay": False}
SELF_ON = {**copy.deepcopy(STATION_VIEW), "publicDisplay": True}


async def with_station(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={**ACCOUNT_DATA, **STATION_DATA}, unique_id="OLDKEY"
    )
    entry.add_to_hass(hass)
    await load(hass, entry)
    return entry


async def open_visibility(hass: HomeAssistant, entry: MockConfigEntry, view: dict):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=copy.deepcopy(view)),
    ):
        return await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "visibility"}
        )


async def test_the_option_is_offered_only_with_a_station(hass: HomeAssistant) -> None:
    account_only = add_entry(hass, ACCOUNT_DATA)
    await load(hass, account_only)
    result = await hass.config_entries.options.async_init(account_only.entry_id)
    assert "visibility" not in result["menu_options"]


async def test_the_form_shows_the_state_the_service_has(hass: HomeAssistant) -> None:
    entry = await with_station(hass)
    form = await open_visibility(hass, entry, SELF_OFF)

    assert form["type"] is FlowResultType.FORM
    assert form["step_id"] == "visibility"
    # Switched off on the website -> the checkbox comes up unticked here too.
    assert form["data_schema"]({})["public_display"] is False


async def test_switching_off_saves_with_the_station_token(hass: HomeAssistant) -> None:
    entry = await with_station(hass)
    form = await open_visibility(hass, entry, SELF_ON)
    assert form["data_schema"]({})["public_display"] is True

    saved = AsyncMock(return_value=False)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_set_visibility", new=saved
    ):
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], {"public_display": False}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    saved.assert_awaited_once_with(False)
    # The measurement mapping is untouched: this switch only changes visibility.
    assert result["data"] == dict(entry.options)


async def test_a_rejected_key_asks_for_re_authentication(hass: HomeAssistant) -> None:
    entry = await with_station(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        outcome = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "visibility"}
        )

    assert outcome["type"] is FlowResultType.ABORT
    assert outcome["reason"] == "reauth_required"


async def test_a_failed_save_says_so_and_does_not_claim_success(hass: HomeAssistant) -> None:
    entry = await with_station(hass)
    form = await open_visibility(hass, entry, SELF_ON)

    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_set_visibility",
        new=AsyncMock(side_effect=ServiceUnavailable("down")),
    ):
        outcome = await hass.config_entries.options.async_configure(
            form["flow_id"], {"public_display": False}
        )

    assert outcome["type"] is FlowResultType.FORM
    assert outcome["errors"] == {"base": "cannot_connect"}
