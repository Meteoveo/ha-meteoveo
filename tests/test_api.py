"""Account, integration-key and home-view requests.

Mirrors test_client.py for the 0.2.0 endpoints. What matters is the same as
there: *why* a request failed decides what Home Assistant does next, and no
password, key or token may end up in an exception message.
"""

from __future__ import annotations

import json

import aiohttp
import pytest

from custom_components.meteoveo.auth import Credentials
from custom_components.meteoveo.client import (
    AccountClient,
    ApiError,
    InvalidCredentials,
    MeteoVeoClient,
    ServiceUnavailable,
)
from custom_components.meteoveo.const import API_BASE, USER_AGENT

PASSWORD = "correct-horse-battery"
TOKEN = "jwt.header.payload"
INTEGRATION_KEY = "mvik_EXAMPLEKEY.example-secret-value"
STATION = Credentials(station_id="MVEXAMPLE1", station_key="station-secret-value")


@pytest.fixture(autouse=True)
def mock_home_view():
    """These tests exercise the real home-view request; do not patch it."""
    yield


class FakeResponse:
    def __init__(self, status: int, payload=None, *, headers=None, raw: str | None = None):
        self.status = status
        self._payload = payload
        self._raw = raw
        self.headers = headers or {}

    async def json(self, **kwargs):
        if self._raw is not None:
            raise json.JSONDecodeError("not json", self._raw, 0)
        if self._payload is None:
            raise aiohttp.ContentTypeError(None, (), message="no body")
        return self._payload

    async def text(self):
        return self._raw or json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Unreachable(FakeResponse):
    def __init__(self, failure: BaseException):
        super().__init__(0)
        self._failure = failure

    async def __aenter__(self):
        raise self._failure


class FakeSession:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self._responses.pop(0) if self._responses else FakeResponse(204)


def everything_said(failure: BaseException) -> str:
    return f"{failure!s} {failure!r} {failure.args!r}"


# --- Account ----------------------------------------------------------------


async def test_signup_sends_consent_and_language() -> None:
    session = FakeSession(FakeResponse(202, {"status": "code_sent"}))
    await AccountClient(session).async_signup(
        "ana@example.com", PASSWORD, marketing=False, lang="ca"
    )
    method, url, kwargs = session.requests[0]
    assert (method, url) == ("POST", f"{API_BASE}/auth/signup")
    assert kwargs["json"] == {
        "email": "ana@example.com",
        "password": PASSWORD,
        "marketingConsent": False,
        "lang": "ca",
    }
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["timeout"] is not None


@pytest.mark.parametrize(
    "status,body,code",
    [
        (400, {"error": {"code": "weak_password"}}, "weak_password"),
        (403, {"error": {"code": "registration_closed"}}, "registration_closed"),
    ],
)
async def test_signup_refusals_carry_their_code(status, body, code) -> None:
    session = FakeSession(FakeResponse(status, body))
    with pytest.raises(ApiError) as caught:
        await AccountClient(session).async_signup(
            "ana@example.com", PASSWORD, marketing=True, lang="es"
        )
    assert caught.value.code == code
    assert PASSWORD not in everything_said(caught.value)


async def test_verify_reports_a_wrong_code() -> None:
    session = FakeSession(FakeResponse(400, {"error": {"code": "invalid_code"}}))
    with pytest.raises(ApiError) as caught:
        await AccountClient(session).async_verify("ana@example.com", "123456")
    assert caught.value.code == "invalid_code"
    assert session.requests[0][2]["json"] == {"email": "ana@example.com", "code": "123456"}


async def test_login_returns_the_token() -> None:
    session = FakeSession(FakeResponse(200, {"token": TOKEN, "role": "user", "level": "free"}))
    token = await AccountClient(session).async_login("ana@example.com", PASSWORD)
    assert token == TOKEN
    assert session.requests[0][1] == f"{API_BASE}/auth/login/password"


async def test_rejected_login_is_invalid_credentials() -> None:
    # The service answers wrong password, unknown account and password-less
    # account the same way.
    session = FakeSession(FakeResponse(401, {"error": "invalid credentials"}))
    with pytest.raises(InvalidCredentials) as caught:
        await AccountClient(session).async_login("ana@example.com", PASSWORD)
    assert PASSWORD not in everything_said(caught.value)


async def test_login_without_a_token_is_an_outage_not_a_success() -> None:
    session = FakeSession(FakeResponse(200, {"role": "user"}))
    with pytest.raises(ServiceUnavailable):
        await AccountClient(session).async_login("ana@example.com", PASSWORD)


@pytest.mark.parametrize(
    "failure",
    [aiohttp.ClientConnectionError("refused"), TimeoutError()],
)
async def test_network_failures_are_outages(failure) -> None:
    session = FakeSession(Unreachable(failure))
    with pytest.raises(ServiceUnavailable) as caught:
        await AccountClient(session).async_login("ana@example.com", PASSWORD)
    assert caught.value.__cause__ is None
    assert PASSWORD not in everything_said(caught.value)


async def test_a_body_that_is_not_json_is_an_outage() -> None:
    session = FakeSession(FakeResponse(200, raw="<html>bad gateway</html>"))
    with pytest.raises(ServiceUnavailable):
        await AccountClient(session).async_login("ana@example.com", PASSWORD)


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_server_side_trouble_is_an_outage(status) -> None:
    session = FakeSession(FakeResponse(status, {"error": {"code": "unavailable"}}))
    with pytest.raises(ServiceUnavailable):
        await AccountClient(session).async_login("ana@example.com", PASSWORD)


async def test_station_creation_uses_the_session_token() -> None:
    session = FakeSession(
        FakeResponse(200, {"stationId": 123, "ingestId": "MVEXAMPLE1", "secret": "s"})
    )
    station = await AccountClient(session).async_create_station(
        TOKEN, name="Casa", lat=38.92, lon=-0.26, sensor_height_cm=200
    )
    assert station["stationId"] == 123
    method, url, kwargs = session.requests[0]
    assert (method, url) == ("POST", f"{API_BASE}/v1/me/stations/direct")
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kwargs["json"] == {"name": "Casa", "lat": 38.92, "lon": -0.26, "sensorHeightCm": 200}


async def test_integration_key_request_shape() -> None:
    session = FakeSession(
        FakeResponse(201, {"keyId": "EXAMPLEKEY", "key": INTEGRATION_KEY, "place": {"name": "X"}})
    )
    issued = await AccountClient(session).async_create_integration_key(
        TOKEN, lat=38.92, lon=-0.26, label="Home", station_ref=123
    )
    assert issued["key"] == INTEGRATION_KEY
    _, url, kwargs = session.requests[0]
    assert url == f"{API_BASE}/v1/me/integration-keys"
    assert kwargs["json"] == {
        "clientKind": "home_assistant",
        "lat": 38.92,
        "lon": -0.26,
        "label": "Home",
        "stationId": 123,
    }


async def test_integration_key_without_station_omits_it() -> None:
    session = FakeSession(FakeResponse(201, {"keyId": "K", "key": INTEGRATION_KEY}))
    await AccountClient(session).async_create_integration_key(
        TOKEN, lat=38.92, lon=-0.26, label="x" * 200, station_ref=None
    )
    sent = session.requests[0][2]["json"]
    assert "stationId" not in sent
    # The service caps labels at 80 characters.
    assert len(sent["label"]) == 80


@pytest.mark.parametrize(
    "status,code", [(400, "invalid_location"), (404, "unknown_station"), (409, "too_many_keys")]
)
async def test_integration_key_refusals(status, code) -> None:
    session = FakeSession(FakeResponse(status, {"error": {"code": code}}))
    with pytest.raises(ApiError) as caught:
        await AccountClient(session).async_create_integration_key(
            TOKEN, lat=0, lon=0, label=None, station_ref=None
        )
    assert caught.value.code == code


async def test_account_deletion_request_and_refusals() -> None:
    session = FakeSession(
        FakeResponse(403, {"error": {"code": "invalid_password"}}),
        FakeResponse(200, {"ok": True}),
    )
    client = AccountClient(session)
    with pytest.raises(ApiError) as caught:
        await client.async_delete_account(TOKEN, password=PASSWORD, confirm="ana@example.com")
    assert caught.value.code == "invalid_password"
    assert PASSWORD not in everything_said(caught.value)

    await client.async_delete_account(TOKEN, password=PASSWORD, confirm="ana@example.com")
    method, url, kwargs = session.requests[1]
    assert (method, url) == ("POST", f"{API_BASE}/v1/me/delete")
    assert kwargs["json"] == {"password": PASSWORD, "confirm": "ana@example.com"}


# --- Home view and the integration key --------------------------------------


async def test_home_uses_the_integration_key_and_the_language() -> None:
    session = FakeSession(FakeResponse(200, {"v": 1}, headers={"ETag": '"abc"'}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    data, etag = await client.async_get_home("en")
    assert data == {"v": 1}
    assert etag == '"abc"'
    method, url, kwargs = session.requests[0]
    assert (method, url) == ("GET", f"{API_BASE}/v1/integration/home")
    assert kwargs["params"] == {"lang": "en"}
    assert kwargs["headers"]["Authorization"] == f"Bearer {INTEGRATION_KEY}"
    assert "If-None-Match" not in kwargs["headers"]


async def test_home_falls_back_to_the_station_token() -> None:
    # Station-key entries (0.1.x) get the forecast too.
    session = FakeSession(FakeResponse(200, {"v": 1}))
    await MeteoVeoClient(session, STATION).async_get_home("es")
    auth = session.requests[0][2]["headers"]["Authorization"]
    assert auth == f"Bearer {STATION.station_id}.{STATION.station_key}"


async def test_home_not_modified_returns_nothing_new() -> None:
    session = FakeSession(FakeResponse(304, None, headers={"ETag": '"abc"'}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    data, etag = await client.async_get_home("es", etag='"abc"')
    assert data is None
    assert etag == '"abc"'
    assert session.requests[0][2]["headers"]["If-None-Match"] == '"abc"'


async def test_home_rejected_key() -> None:
    session = FakeSession(FakeResponse(401, {"error": {"code": "invalid_key"}}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    with pytest.raises(InvalidCredentials) as caught:
        await client.async_get_home("es")
    assert INTEGRATION_KEY not in everything_said(caught.value)


async def test_home_that_is_not_an_object_is_an_outage() -> None:
    session = FakeSession(FakeResponse(200, ["not", "an", "object"]))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    with pytest.raises(ServiceUnavailable):
        await client.async_get_home("es")


async def test_location_change() -> None:
    session = FakeSession(FakeResponse(200, {"place": {"name": "Gandia"}}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    place = await client.async_set_location(38.97, -0.18)
    assert place == {"name": "Gandia"}
    method, url, kwargs = session.requests[0]
    assert (method, url) == ("PUT", f"{API_BASE}/v1/integration/location")
    assert kwargs["json"] == {"lat": 38.97, "lon": -0.18}


async def test_location_outside_the_service_area() -> None:
    session = FakeSession(FakeResponse(400, {"error": {"code": "invalid_location"}}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    with pytest.raises(ApiError) as caught:
        await client.async_set_location(48.85, 2.35)
    assert caught.value.code == "invalid_location"


async def test_location_change_limit_is_a_reason_not_an_outage() -> None:
    """ADR-0834 D2: too many place changes -> 429 with a code; the flow shows it."""
    session = FakeSession(FakeResponse(429, {"error": {"code": "location_change_limit"}}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    with pytest.raises(ApiError) as caught:
        await client.async_set_location(40.42, -3.7)
    assert caught.value.code == "location_change_limit"


async def test_a_plain_429_is_still_an_outage() -> None:
    """ADR-0834 D3: a quota 429 is temporary -- retried on the next round."""
    session = FakeSession(FakeResponse(429, {"error": {"code": "rate_limited"}}))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    with pytest.raises(ServiceUnavailable):
        await client.async_get_home("es")


async def test_revoke_uses_a_short_timeout() -> None:
    session = FakeSession(FakeResponse(204))
    client = MeteoVeoClient(session, integration_key=INTEGRATION_KEY)
    await client.async_revoke_key()
    method, url, kwargs = session.requests[0]
    assert (method, url) == ("DELETE", f"{API_BASE}/v1/integration/key")
    assert kwargs["timeout"].total <= 10
