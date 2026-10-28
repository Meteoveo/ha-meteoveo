"""Config flow, exercised through Home Assistant itself."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.meteoveo.client import InvalidCredentials, ServiceUnavailable
from custom_components.meteoveo.const import (
    CONF_MEASUREMENTS,
    CONF_PRESSURE_KIND,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DOMAIN,
)
from custom_components.meteoveo.wu_payload import PRESSURE_ABSOLUTE

CREDENTIALS = {CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "key-value"}


async def start(hass: HomeAssistant):
    """Open the flow and take the station-key option from the first menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "station_key"}
    )


async def test_the_first_screen_offers_all_three_routes(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["create_account", "login", "station_key"]


async def test_full_setup_creates_an_entry(hass: HomeAssistant, mock_station_view) -> None:
    result = await start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "station_key"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["step_id"] == "measurements"

    # Nothing selected: a station with no matching entities must still finish.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garden"
    assert result["data"] == CREDENTIALS
    assert result["options"] == {
        CONF_MEASUREMENTS: {},
        CONF_PRESSURE_KIND: PRESSURE_ABSOLUTE,
    }


async def test_credentials_are_checked_before_the_entry_is_created(
    hass: HomeAssistant, mock_station_view
) -> None:
    result = await start(hass)
    await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    mock_station_view.assert_awaited_once()


@pytest.mark.parametrize(
    "failure,expected",
    [
        (InvalidCredentials("no"), "invalid_auth"),
        (ServiceUnavailable("down"), "cannot_connect"),
        (TimeoutError(), "unknown"),
    ],
)
async def test_failures_are_reported_distinctly(
    hass: HomeAssistant, failure, expected
) -> None:
    with patch(
        "custom_components.meteoveo.config_flow._verify", new=AsyncMock(side_effect=failure)
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_recovers_after_a_failed_attempt(hass: HomeAssistant) -> None:
    # A wrong key must not be a dead end: correcting it has to work without
    # restarting the flow.
    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(return_value={"station": {"name": "Garden"}}),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_station_cannot_be_added_twice(
    hass: HomeAssistant, mock_station_view
) -> None:
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    await hass.config_entries.flow.async_configure(result["flow_id"], {})

    # Same station, different case and padding: still the same station.
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATION_ID: "  mvexample1 ", CONF_STATION_KEY: "key-value"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_title_falls_back_to_the_station_id(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.meteoveo.config_flow._verify", new=AsyncMock(return_value={})
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["title"] == "MVEXAMPLE1"


async def test_every_form_carries_its_docs_link(
    hass: HomeAssistant, mock_station_view
) -> None:
    # Each step's description ends in a link to the relevant knowledge-base
    # page; the placeholder must actually be supplied or the raw "{docs_url}"
    # shows up in the dialog.
    from custom_components.meteoveo.const import (
        DOCS_MEASUREMENTS_URL,
        DOCS_SETUP_URL,
    )

    result = await start(hass)
    assert result["description_placeholders"]["docs_url"] == DOCS_SETUP_URL

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["step_id"] == "measurements"
    assert result["description_placeholders"]["docs_url"] == DOCS_MEASUREMENTS_URL


class _UnreachableRequest:
    async def __aenter__(self):
        import aiohttp

        raise aiohttp.ClientConnectionError("connection refused")

    async def __aexit__(self, *exc):
        return False


class _UnreachableSession:
    def get(self, url, **kwargs):
        return _UnreachableRequest()


async def test_an_unreachable_service_is_reported_as_such(hass: HomeAssistant) -> None:
    # Through the real client, not a patched _verify: a refused connection
    # must reach the screen as "Could not reach MeteoVeo", not as "unknown".
    with patch(
        "custom_components.meteoveo.config_flow.async_get_clientsession",
        return_value=_UnreachableSession(),
    ):
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
