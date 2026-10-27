"""Account entries after setup: re-authentication, options, removal,
account deletion, diagnostics, and the bundled card."""

from __future__ import annotations

import copy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoveo.client import (
    ApiError,
    InvalidCredentials,
    ServiceUnavailable,
)
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
from test_account_flow import EMAIL, PASSWORD, TOKEN, Service

KEY = "mvik_OLDKEY.old-secret"
ACCOUNT_DATA = {
    CONF_INTEGRATION_KEY: KEY,
    CONF_KEY_ID: "OLDKEY",
    CONF_EMAIL: EMAIL,
    "latitude": 38.92,
    "longitude": -0.26,
}
STATION_DATA = {
    CONF_STATION_ID: "MVEXAMPLE1",
    CONF_STATION_KEY: "station-secret",
    CONF_STATION_REF: 123,
}
NEW_KEY = {"keyId": "NEWKEY", "key": "mvik_NEWKEY.new-secret", "place": {"name": "Villa Ejemplo"}}


def add_entry(hass: HomeAssistant, data: dict, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options=options or {},
        unique_id="OLDKEY",
        title="Villa Ejemplo",
    )
    entry.add_to_hass(hass)
    return entry


async def load(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=copy.deepcopy(STATION_VIEW)),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


# --- Re-authentication -------------------------------------------------------


async def test_reauth_signs_in_and_replaces_the_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_login"
    # The email is offered back; only the password needs typing.
    suggested = {
        str(key): (key.description or {}).get("suggested_value")
        for key in result["data_schema"].schema
    }
    assert suggested["email"] == EMAIL

    with Service(async_create_integration_key=AsyncMock(return_value=dict(NEW_KEY))) as service:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_INTEGRATION_KEY] == NEW_KEY["key"]
    assert entry.data[CONF_KEY_ID] == "NEWKEY"
    # Same connection: the unique id (and so every entity id) is kept.
    assert entry.unique_id == "OLDKEY"
    service.async_delete_integration_key.assert_awaited_once_with(TOKEN, "OLDKEY")
    kwargs = service.async_create_integration_key.await_args.kwargs
    assert (kwargs["lat"], kwargs["lon"], kwargs["station_ref"]) == (38.92, -0.26, None)


async def test_reauth_refuses_another_account(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    result = await entry.start_reauth_flow(hass)
    with Service() as service:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": "otra@example.com", "password": PASSWORD}
        )
    assert result["errors"] == {"email": "wrong_account"}
    service.async_login.assert_not_awaited()


async def test_reauth_wrong_password(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    result = await entry.start_reauth_flow(hass)
    with Service(async_login=AsyncMock(side_effect=InvalidCredentials("no"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": EMAIL, "password": "wrong"}
        )
    assert result["errors"] == {"base": "invalid_login"}
    assert entry.data[CONF_INTEGRATION_KEY] == KEY


async def test_reauth_renews_a_rejected_station_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass, {**ACCOUNT_DATA, **STATION_DATA})
    result = await entry.start_reauth_flow(hass)
    with Service(
        async_create_integration_key=AsyncMock(return_value=dict(NEW_KEY))
    ) as service, patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    service.async_renew_ingest_key.assert_awaited_once_with(TOKEN, 123)
    assert entry.data[CONF_STATION_KEY] == "renewed"
    assert entry.data[CONF_STATION_ID] == "MVEXAMPLE1"
    assert service.async_create_integration_key.await_args.kwargs["station_ref"] == 123


async def test_reauth_keeps_a_working_station_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass, {**ACCOUNT_DATA, **STATION_DATA})
    result = await entry.start_reauth_flow(hass)
    with Service(
        async_create_integration_key=AsyncMock(return_value=dict(NEW_KEY))
    ) as service, patch(
        "custom_components.meteoveo.config_flow._verify",
        new=AsyncMock(return_value=STATION_VIEW),
    ):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"email": EMAIL, "password": PASSWORD}
        )
        await hass.async_block_till_done()
    service.async_renew_ingest_key.assert_not_awaited()
    assert entry.data[CONF_STATION_KEY] == "station-secret"


async def test_a_rejected_upload_key_on_an_account_entry_opens_sign_in(
    hass: HomeAssistant,
) -> None:
    entry = add_entry(hass, {**ACCOUNT_DATA, **STATION_DATA})
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # The forecast still loads; the station view's refusal asks to sign in.
    assert entry.state is ConfigEntryState.LOADED
    flows = [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]
    assert flows and flows[0]["step_id"] == "reauth_login"


# --- Options -----------------------------------------------------------------


async def open_options(hass: HomeAssistant, entry: MockConfigEntry, option: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": option}
    )


async def test_options_menu_depends_on_the_entry(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # ADR-0866 D9: without a station, the station door is offered here.
    assert result["menu_options"] == ["location", "add_station", "delete_account"]

    with_station = MockConfigEntry(
        domain=DOMAIN, data={**ACCOUNT_DATA, **STATION_DATA}, unique_id="OTHER"
    )
    with_station.add_to_hass(hass)
    await load(hass, with_station)
    result = await hass.config_entries.options.async_init(with_station.entry_id)
    assert result["menu_options"] == ["location", "measurements", "delete_account"]


async def test_changing_the_place(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_options(hass, entry, "location")
    assert result["step_id"] == "location"

    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_set_location",
        new=AsyncMock(return_value={"name": "Otro Pueblo", "lat": 39.47, "lon": -0.38}),
    ) as moved:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"location": {"latitude": 39.4699, "longitude": -0.3763}}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    moved.assert_awaited_once_with(39.47, -0.38)
    assert entry.title == "Otro Pueblo"
    assert (entry.data["latitude"], entry.data["longitude"]) == (39.47, -0.38)
    assert entry.state is ConfigEntryState.LOADED


async def test_changing_the_place_outside_the_service_area(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_options(hass, entry, "location")
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_set_location",
        new=AsyncMock(side_effect=ApiError(400, "invalid_location")),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"location": {"latitude": 39.0, "longitude": -1.0}}
        )
    assert result["errors"] == {"location": "invalid_location"}


async def test_changing_the_place_too_often(hass: HomeAssistant) -> None:
    """ADR-0834 D2: the place may change at most 3 times a day / 10 a month."""
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_options(hass, entry, "location")
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_set_location",
        new=AsyncMock(side_effect=ApiError(429, "location_change_limit")),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"location": {"latitude": 39.0, "longitude": -1.0}}
        )
    assert result["errors"] == {"base": "location_change_limit"}


async def test_changing_the_place_with_a_revoked_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    result = await open_options(hass, entry, "location")
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_set_location",
        new=AsyncMock(side_effect=InvalidCredentials("no")),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"location": {"latitude": 39.0, "longitude": -1.0}}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_required"


async def test_measurements_option_keeps_other_options(hass: HomeAssistant) -> None:
    entry = add_entry(
        hass, {**ACCOUNT_DATA, **STATION_DATA}, options={CONF_MEASUREMENTS: {}}
    )
    await load(hass, entry)
    result = await open_options(hass, entry, "measurements")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"humidity": "sensor.h"}
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_MEASUREMENTS] == {"humidity": "sensor.h"}


# --- Deleting the account ----------------------------------------------------


async def delete_form(hass: HomeAssistant, entry: MockConfigEntry, **values):
    result = await open_options(hass, entry, "delete_account")
    assert result["step_id"] == "delete_account"
    form = {"email": EMAIL, "password": PASSWORD, "confirm": EMAIL}
    form.update(values)
    return await hass.config_entries.options.async_configure(result["flow_id"], form)


async def test_deleting_the_account(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    with Service() as service, patch(
        "custom_components.meteoveo.MeteoVeoClient.async_revoke_key", new=AsyncMock()
    ):
        result = await delete_form(hass, entry, confirm=f" {EMAIL.upper()} ")
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "account_deleted"
    service.async_delete_account.assert_awaited_once_with(
        TOKEN, password=PASSWORD, confirm=EMAIL.upper()
    )
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    notifications = hass.data["persistent_notification"]
    note = notifications[f"{DOMAIN}_account_deleted"]
    # The translated text, not the built-in fallback.
    assert note["title"] == "MeteoVeo account deleted"
    assert "App Store or Google Play subscription is not cancelled" in note["message"]


async def test_deletion_needs_the_email_typed_twice(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    with Service() as service:
        result = await delete_form(hass, entry, confirm="other@example.com")
    assert result["errors"] == {"confirm": "confirm_mismatch"}
    service.async_login.assert_not_awaited()
    assert hass.config_entries.async_get_entry(entry.entry_id) is not None


@pytest.mark.parametrize(
    "failure,errors",
    [
        (ApiError(403, "invalid_password"), {"password": "invalid_password"}),
        (ApiError(400, "confirm_mismatch"), {"confirm": "confirm_mismatch"}),
        (ApiError(400, "password_required"), {"base": "password_required"}),
        (ServiceUnavailable("down"), {"base": "cannot_connect"}),
    ],
)
async def test_deletion_refusals(hass: HomeAssistant, failure, errors) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    with Service(async_delete_account=AsyncMock(side_effect=failure)):
        result = await delete_form(hass, entry)
    assert result["errors"] == errors
    assert hass.config_entries.async_get_entry(entry.entry_id) is not None


async def test_deletion_with_a_wrong_password(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    with Service(async_login=AsyncMock(side_effect=InvalidCredentials("no"))) as service:
        result = await delete_form(hass, entry)
    assert result["errors"] == {"base": "invalid_login"}
    service.async_delete_account.assert_not_awaited()


# --- Removal -----------------------------------------------------------------


async def test_removal_revokes_the_key(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    with patch(
        "custom_components.meteoveo.MeteoVeoClient.async_revoke_key", new=AsyncMock()
    ) as revoke:
        await hass.config_entries.async_remove(entry.entry_id)
    revoke.assert_awaited_once()


@pytest.mark.parametrize("failure", [ServiceUnavailable("down"), InvalidCredentials("no"), RuntimeError()])
async def test_removal_never_fails_on_the_network(hass: HomeAssistant, failure) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    await load(hass, entry)
    with patch(
        "custom_components.meteoveo.MeteoVeoClient.async_revoke_key",
        new=AsyncMock(side_effect=failure),
    ):
        result = await hass.config_entries.async_remove(entry.entry_id)
    assert result == {"require_restart": False}


async def test_removing_a_station_key_entry_revokes_nothing(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATION_ID: "MVEXAMPLE1", CONF_STATION_KEY: "k"},
        unique_id="mvexample1",
    )
    entry.add_to_hass(hass)
    await load(hass, entry)
    with patch(
        "custom_components.meteoveo.MeteoVeoClient.async_revoke_key", new=AsyncMock()
    ) as revoke:
        await hass.config_entries.async_remove(entry.entry_id)
    revoke.assert_not_awaited()


# --- Diagnostics -------------------------------------------------------------


async def test_diagnostics_redact_every_secret(hass: HomeAssistant) -> None:
    from custom_components.meteoveo.diagnostics import async_get_config_entry_diagnostics

    entry = add_entry(hass, {**ACCOUNT_DATA, **STATION_DATA})
    await load(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    text = repr(diagnostics)
    for secret in (KEY, "OLDKEY", EMAIL, "station-secret", "MVEXAMPLE1", "38.92", "-0.26"):
        assert secret not in text, secret
    assert diagnostics["home"]["last_update_success"] is True
    assert diagnostics["home"]["data"]["current"]["condition"] == "partlycloudy"


# --- Card --------------------------------------------------------------------


async def test_card_is_not_registered_when_it_is_not_bundled(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    from custom_components.meteoveo.card import async_register_card

    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    assert await async_register_card(hass, tmp_path / "missing.js") is False
    hass.http.async_register_static_paths.assert_not_awaited()


async def test_card_is_served_and_loaded_with_the_version(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    from custom_components.meteoveo.card import CARD_URL, async_register_card
    from custom_components.meteoveo.const import VERSION

    card = tmp_path / "meteoveo-card.js"
    card.write_text("// card", encoding="utf-8")
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch("custom_components.meteoveo.card.add_extra_js_url") as add_js:
        assert await async_register_card(hass, card) is True

    (config,) = hass.http.async_register_static_paths.await_args.args[0]
    assert config.url_path == CARD_URL
    assert config.path == str(card)
    add_js.assert_called_once_with(hass, f"{CARD_URL}?v={VERSION}")


def test_version_constant_matches_the_manifest() -> None:
    import json

    from custom_components.meteoveo.const import USER_AGENT, VERSION

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "custom_components/meteoveo/manifest.json").read_text()
    )
    assert VERSION == manifest["version"]
    assert USER_AGENT == f"ha-meteoveo/{manifest['version']}"


def test_manifest_declares_what_the_card_needs() -> None:
    import json

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "custom_components/meteoveo/manifest.json").read_text()
    )
    assert {"http", "frontend"} <= set(manifest["dependencies"])


async def test_deleting_the_account_removes_all_of_its_entries(hass: HomeAssistant) -> None:
    entry = add_entry(hass, ACCOUNT_DATA)
    second = MockConfigEntry(
        domain=DOMAIN, data={**ACCOUNT_DATA, CONF_KEY_ID: "K2"}, unique_id="K2"
    )
    second.add_to_hass(hass)
    unrelated = MockConfigEntry(
        domain=DOMAIN, data={**ACCOUNT_DATA, CONF_EMAIL: "otra@example.com"}, unique_id="K3"
    )
    unrelated.add_to_hass(hass)
    await load(hass, entry)
    with Service(), patch(
        "custom_components.meteoveo.MeteoVeoClient.async_revoke_key", new=AsyncMock()
    ):
        await delete_form(hass, entry)
        await hass.async_block_till_done()
    remaining = {e.entry_id for e in hass.config_entries.async_entries(DOMAIN)}
    assert remaining == {unrelated.entry_id}
