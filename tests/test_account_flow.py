"""Setup by creating an account or signing in (0.2.0).

The service is mocked at the AccountClient boundary; the request shapes
themselves are covered in test_api.py.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

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
    CONF_PRESSURE_KIND,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_REF,
    DOMAIN,
)
from custom_components.meteoveo.wu_payload import PRESSURE_ABSOLUTE

EMAIL = "ana@example.com"
PASSWORD = "correct-horse-battery"
TOKEN = "jwt.example.token"
ISSUED = {
    "keyId": "EXAMPLEKEY",
    "key": "mvik_EXAMPLEKEY.example-secret",
    "place": {"name": "Villa Ejemplo", "lat": 38.92, "lon": -0.26},
}
STATION = {"stationId": 123, "ingestId": "MVEXAMPLE1", "secret": "station-secret"}
HOME = {"location": {"latitude": 38.9234, "longitude": -0.2612}}

A = "custom_components.meteoveo.client.AccountClient."


class Service:
    """Patches every AccountClient call; each attribute is the AsyncMock."""

    def __init__(self, **overrides):
        self._stack = ExitStack()
        defaults = {
            "async_signup": AsyncMock(return_value=None),
            "async_verify": AsyncMock(return_value=None),
            "async_login": AsyncMock(return_value=TOKEN),
            "async_create_station": AsyncMock(return_value=dict(STATION)),
            "async_create_integration_key": AsyncMock(return_value=dict(ISSUED)),
            "async_delete_integration_key": AsyncMock(return_value=None),
            "async_renew_ingest_key": AsyncMock(return_value={"secret": "renewed"}),
            "async_delete_account": AsyncMock(return_value=None),
        }
        defaults.update(overrides)
        self.mocks = defaults

    def __enter__(self):
        for name, mock in self.mocks.items():
            self._stack.enter_context(patch(A + name, new=mock))
        return self

    def __exit__(self, *exc):
        self._stack.close()

    def __getattr__(self, name):
        return self.mocks[name]


@pytest.fixture(autouse=True)
def station_view():
    """Entries created with a station load its view right away."""
    from conftest import STATION_VIEW

    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=AsyncMock(return_value=STATION_VIEW),
    ):
        yield


@pytest.fixture(autouse=True)
def home_in_spain(hass: HomeAssistant):
    hass.config.latitude = 38.9234
    hass.config.longitude = -0.2612
    hass.config.location_name = "Casa"
    hass.config.language = "ca"


async def menu(hass: HomeAssistant, option: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": option}
    )


async def sign_up(hass: HomeAssistant, **form):
    result = await menu(hass, "create_account")
    assert result["step_id"] == "create_account"
    values = {"email": EMAIL, "password": PASSWORD, "accept_terms": True, "marketing": False}
    values.update(form)
    return await hass.config_entries.flow.async_configure(result["flow_id"], values)


async def configure(hass, result, values):
    return await hass.config_entries.flow.async_configure(result["flow_id"], values)


# --- Creating an account -----------------------------------------------------


async def test_new_account_without_station(hass: HomeAssistant) -> None:
    with Service() as service:
        result = await sign_up(hass)
        assert result["step_id"] == "verify_code"
        assert result["description_placeholders"]["email"] == EMAIL
        service.async_signup.assert_awaited_once_with(
            EMAIL, PASSWORD, marketing=False, lang="ca"
        )

        result = await configure(hass, result, {"code": " 123 456 "})
        service.async_verify.assert_awaited_once_with(EMAIL, "123456")
        service.async_login.assert_awaited_once_with(EMAIL, PASSWORD)
        assert result["step_id"] == "location"

        result = await configure(hass, result, HOME)
        assert result["step_id"] == "has_station"

        result = await configure(hass, result, {"has_station": False})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Villa Ejemplo"
    assert result["result"].unique_id == "EXAMPLEKEY"
    assert result["data"] == {
        CONF_INTEGRATION_KEY: ISSUED["key"],
        CONF_KEY_ID: "EXAMPLEKEY",
        CONF_EMAIL: EMAIL,
        "latitude": 38.92,
        "longitude": -0.26,
    }
    # Neither the password nor the session token is stored.
    stored = repr(result["data"]) + repr(result["options"])
    assert PASSWORD not in stored and TOKEN not in stored

    kwargs = service.async_create_integration_key.await_args.kwargs
    # The home's exact position is not sent for the forecast: ~1 km is enough.
    assert (kwargs["lat"], kwargs["lon"]) == (38.92, -0.26)
    assert kwargs["label"] == "Casa"
    assert kwargs["station_ref"] is None
    service.async_create_station.assert_not_awaited()


async def test_marketing_is_separate_and_off_unless_ticked(hass: HomeAssistant) -> None:
    with Service() as service:
        await sign_up(hass, marketing=True)
    assert service.async_signup.await_args.kwargs["marketing"] is True


@pytest.mark.parametrize(
    "form,field,error",
    [
        ({"accept_terms": False}, "accept_terms", "terms_required"),
        ({"password": "short"}, "password", "password_too_short"),
        ({"email": "not-an-address"}, "email", "invalid_email"),
    ],
)
async def test_sign_up_form_is_checked_before_anything_is_sent(
    hass: HomeAssistant, form, field, error
) -> None:
    with Service() as service:
        result = await sign_up(hass, **form)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {field: error}
    service.async_signup.assert_not_awaited()


async def test_weak_password(hass: HomeAssistant) -> None:
    with Service(async_signup=AsyncMock(side_effect=ApiError(400, "weak_password"))):
        result = await sign_up(hass)
    assert result["errors"] == {"password": "weak_password"}


async def test_registration_closed(hass: HomeAssistant) -> None:
    with Service(async_signup=AsyncMock(side_effect=ApiError(403, "registration_closed"))):
        result = await sign_up(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "registration_closed"


async def test_sign_up_while_the_service_is_down(hass: HomeAssistant) -> None:
    with Service(async_signup=AsyncMock(side_effect=ServiceUnavailable("down"))):
        result = await sign_up(hass)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_wrong_code_then_right_code(hass: HomeAssistant) -> None:
    verify = AsyncMock(side_effect=[ApiError(400, "invalid_code"), None])
    with Service(async_verify=verify):
        result = await sign_up(hass)
        result = await configure(hass, result, {"code": "000000"})
        assert result["errors"] == {"code": "invalid_code"}
        result = await configure(hass, result, {"code": "123456"})
    assert result["step_id"] == "location"


async def test_code_is_not_reused_when_the_sign_in_after_it_failed(
    hass: HomeAssistant,
) -> None:
    login = AsyncMock(side_effect=[ServiceUnavailable("down"), TOKEN])
    with Service(async_login=login) as service:
        result = await sign_up(hass)
        result = await configure(hass, result, {"code": "123456"})
        assert result["errors"] == {"base": "cannot_connect"}
        result = await configure(hass, result, {"code": "123456"})
    assert result["step_id"] == "location"
    service.async_verify.assert_awaited_once()


# --- Signing in --------------------------------------------------------------


async def test_existing_account_with_a_station(hass: HomeAssistant) -> None:
    with Service() as service:
        result = await menu(hass, "login")
        assert result["step_id"] == "login"
        result = await configure(hass, result, {"email": f" {EMAIL} ", "password": PASSWORD})
        assert result["step_id"] == "location"
        result = await configure(hass, result, HOME)
        result = await configure(hass, result, {"has_station": True})
        assert result["step_id"] == "station_details"
        assert result["data_schema"]({})["station_name"] == "Casa"
        assert result["data_schema"]({})["sensor_height_cm"] == 200
        result = await configure(
            hass, result, {"station_name": "Jardín", "sensor_height_cm": 180}
        )
        assert result["step_id"] == "measurements"
        result = await configure(hass, result, {"temperature": "sensor.outside"})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STATION_ID] == "MVEXAMPLE1"
    assert result["data"][CONF_STATION_KEY] == "station-secret"
    assert result["data"][CONF_STATION_REF] == 123
    assert result["options"] == {
        CONF_MEASUREMENTS: {"temperature": "sensor.outside"},
        CONF_PRESSURE_KIND: PRESSURE_ABSOLUTE,
    }
    station_kwargs = service.async_create_station.await_args.kwargs
    assert station_kwargs["name"] == "Jardín"
    assert station_kwargs["sensor_height_cm"] == 180
    assert service.async_create_integration_key.await_args.kwargs["station_ref"] == 123


async def test_rejected_sign_in_explains_password_less_accounts(hass: HomeAssistant) -> None:
    with Service(async_login=AsyncMock(side_effect=InvalidCredentials("no"))):
        result = await menu(hass, "login")
        result = await configure(hass, result, {"email": EMAIL, "password": PASSWORD})
    assert result["errors"] == {"base": "invalid_login"}


async def test_place_outside_the_service_area_is_refused_on_the_spot(
    hass: HomeAssistant,
) -> None:
    with Service() as service:
        result = await menu(hass, "login")
        result = await configure(hass, result, {"email": EMAIL, "password": PASSWORD})
        result = await configure(
            hass, result, {"location": {"latitude": 48.85, "longitude": 2.35}}
        )
    assert result["step_id"] == "location"
    assert result["errors"] == {"location": "invalid_location"}
    service.async_create_integration_key.assert_not_awaited()


async def test_a_failed_key_request_does_not_create_a_second_station(
    hass: HomeAssistant,
) -> None:
    create_key = AsyncMock(side_effect=[ServiceUnavailable("down"), dict(ISSUED)])
    with Service(async_create_integration_key=create_key) as service:
        result = await menu(hass, "login")
        result = await configure(hass, result, {"email": EMAIL, "password": PASSWORD})
        result = await configure(hass, result, HOME)
        result = await configure(hass, result, {"has_station": True})
        result = await configure(hass, result, {"station_name": "X", "sensor_height_cm": 200})
        result = await configure(hass, result, {})
        assert result["step_id"] == "measurements"
        assert result["errors"] == {"base": "cannot_connect"}
        result = await configure(hass, result, {})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    service.async_create_station.assert_awaited_once()


async def test_too_many_keys(hass: HomeAssistant) -> None:
    create_key = AsyncMock(side_effect=ApiError(409, "too_many_keys"))
    with Service(async_create_integration_key=create_key):
        result = await menu(hass, "login")
        result = await configure(hass, result, {"email": EMAIL, "password": PASSWORD})
        result = await configure(hass, result, HOME)
        result = await configure(hass, result, {"has_station": False})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "too_many_keys"


async def test_service_refuses_the_place(hass: HomeAssistant) -> None:
    create_key = AsyncMock(side_effect=ApiError(400, "invalid_location"))
    with Service(async_create_integration_key=create_key):
        result = await menu(hass, "login")
        result = await configure(hass, result, {"email": EMAIL, "password": PASSWORD})
        result = await configure(hass, result, HOME)
        result = await configure(hass, result, {"has_station": False})
    assert result["step_id"] == "location"
    assert result["errors"] == {"location": "invalid_location"}


async def test_session_expired_while_the_flow_was_open(hass: HomeAssistant) -> None:
    create_key = AsyncMock(side_effect=InvalidCredentials("expired"))
    with Service(async_create_integration_key=create_key):
        result = await menu(hass, "login")
        result = await configure(hass, result, {"email": EMAIL, "password": PASSWORD})
        result = await configure(hass, result, HOME)
        result = await configure(hass, result, {"has_station": False})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "session_expired"


async def test_every_account_form_carries_its_placeholders(hass: HomeAssistant) -> None:
    from custom_components.meteoveo.const import PRIVACY_URL, TERMS_URL

    result = await menu(hass, "create_account")
    placeholders = result["description_placeholders"]
    assert placeholders["terms_url"] == TERMS_URL
    assert placeholders["privacy_url"] == PRIVACY_URL
    assert "docs_url" in placeholders
