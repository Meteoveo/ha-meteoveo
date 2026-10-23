"""API client behaviour.

The distinctions that matter here are about *why* a request failed. Wrong
credentials must lead to a re-authentication prompt; a service outage must
not, or every hiccup would ask the user to type their key again.
"""

from __future__ import annotations

import traceback

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from custom_components.meteoveo.auth import Credentials
from custom_components.meteoveo.client import (
    InvalidCredentials,
    MeteoVeoClient,
    ServiceUnavailable,
)

CREDS = Credentials(station_id="MVEXAMPLE1", station_key="s3cret-key-value")


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = ""):
        self.status = status
        self._payload = payload or {}
        self._text = text

    async def json(self):
        return self._payload

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Records requests and replays canned responses."""

    def __init__(self, *responses: FakeResponse):
        self._responses = list(responses)
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        return self._responses.pop(0) if self._responses else FakeResponse(200)

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)


class UnreachableResponse(FakeResponse):
    """A request that fails before the service answers.

    aiohttp raises when the request context is entered, not from ``get()``.
    """

    def __init__(self, failure: BaseException):
        super().__init__(0)
        self._failure = failure

    async def __aenter__(self):
        raise self._failure


class UnreadableResponse(FakeResponse):
    """A 200 whose body is not JSON -- typically a proxy's error page."""

    def __init__(self, failure: BaseException):
        super().__init__(200)
        self._failure = failure

    async def json(self):
        raise self._failure


def request_info_carrying_the_key() -> aiohttp.RequestInfo:
    # The upload protocol puts the key in the query string, and aiohttp puts
    # the request URL into its exception messages.
    url = URL(
        f"https://example.invalid/upload?ID={CREDS.station_id}&PASSWORD={CREDS.station_key}"
    )
    return aiohttp.RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)


NETWORK_FAILURES = [
    pytest.param(aiohttp.ClientConnectionError("connection refused"), id="refused"),
    pytest.param(aiohttp.ServerDisconnectedError(), id="disconnected"),
    pytest.param(TimeoutError(), id="timeout"),
]


class TestStationView:
    @pytest.mark.asyncio
    async def test_reads_the_station_view(self):
        payload = {
            "station": {"name": "Garden", "lat": 38.98, "lon": -0.17},
            "model": {"status": "ready", "model": "icon", "mae": 1.2},
            "upload": {"lastSeenAt": "2026-08-20T10:00:00Z", "acceptedCount": 7},
        }
        session = FakeSession(FakeResponse(200, payload))
        client = MeteoVeoClient(session, CREDS)

        view = await client.async_get_station()

        assert view["station"]["name"] == "Garden"
        assert view["model"]["model"] == "icon"

    @pytest.mark.asyncio
    async def test_authenticates_with_a_header_not_a_query_string(self):
        session = FakeSession(FakeResponse(200, {"station": {}}))
        await MeteoVeoClient(session, CREDS).async_get_station()

        _, url, kwargs = session.requests[0]
        assert "s3cret-key-value" not in url
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_does_not_send_coordinates(self):
        # The station's position comes from the service, keyed by the token.
        # Sending our own would be meaningless and could only ever disagree.
        session = FakeSession(FakeResponse(200, {"station": {}}))
        await MeteoVeoClient(session, CREDS).async_get_station()

        _, url, kwargs = session.requests[0]
        assert "lat=" not in url
        assert "params" not in kwargs or "lat" not in (kwargs.get("params") or {})


class TestFailureModes:
    """Wrong key and service outage are different problems."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403])
    async def test_rejected_credentials_raise_invalid_credentials(self, status):
        session = FakeSession(FakeResponse(status))
        with pytest.raises(InvalidCredentials):
            await MeteoVeoClient(session, CREDS).async_get_station()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_server_trouble_raises_service_unavailable(self, status):
        # Not InvalidCredentials: an outage must never prompt the user to
        # re-enter a key that is perfectly fine.
        session = FakeSession(FakeResponse(status))
        with pytest.raises(ServiceUnavailable):
            await MeteoVeoClient(session, CREDS).async_get_station()

    @pytest.mark.asyncio
    async def test_error_messages_never_contain_the_key(self):
        session = FakeSession(FakeResponse(500, text=f"failed for key={CREDS.station_key}"))
        with pytest.raises(ServiceUnavailable) as caught:
            await MeteoVeoClient(session, CREDS).async_get_station()
        assert CREDS.station_key not in str(caught.value)


class TestNetworkFailures:
    """No answer at all is an outage too -- never a credential problem."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", NETWORK_FAILURES)
    async def test_unreachable_station_view_raises_service_unavailable(self, failure):
        session = FakeSession(UnreachableResponse(failure))
        with pytest.raises(ServiceUnavailable):
            await MeteoVeoClient(session, CREDS).async_get_station()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", NETWORK_FAILURES)
    async def test_unreachable_upload_raises_service_unavailable(self, failure):
        session = FakeSession(UnreachableResponse(failure))
        with pytest.raises(ServiceUnavailable):
            await MeteoVeoClient(session, CREDS).async_upload(
                {"tempf": 70.0}, now_iso="2026-08-20 10:00:00"
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure",
        [
            pytest.param(ValueError("Expecting value: line 1 column 1"), id="not-json"),
            pytest.param(
                aiohttp.ContentTypeError(request_info_carrying_the_key(), ()),
                id="wrong-content-type",
            ),
        ],
    )
    async def test_a_body_that_is_not_json_is_an_outage(self, failure):
        session = FakeSession(UnreadableResponse(failure))
        with pytest.raises(ServiceUnavailable):
            await MeteoVeoClient(session, CREDS).async_get_station()

    @pytest.mark.asyncio
    async def test_a_network_failure_never_carries_the_key_into_a_traceback(self):
        failure = aiohttp.ClientResponseError(
            request_info_carrying_the_key(), (), status=0, message="connection dropped"
        )
        session = FakeSession(UnreachableResponse(failure))
        with pytest.raises(ServiceUnavailable) as caught:
            await MeteoVeoClient(session, CREDS).async_upload(
                {"tempf": 70.0}, now_iso="2026-08-20 10:00:00"
            )
        printed = "".join(traceback.format_exception(caught.value))
        assert CREDS.station_key not in printed


class TestUpload:
    @pytest.mark.asyncio
    async def test_upload_reports_success(self):
        session = FakeSession(FakeResponse(200, text="success"))
        client = MeteoVeoClient(session, CREDS)

        assert await client.async_upload({"tempf": 70.0}, now_iso="2026-08-20 10:00:00") is True

    @pytest.mark.asyncio
    async def test_upload_with_nothing_to_send_is_skipped(self):
        # An empty upload would still cost a request and would reset nothing.
        session = FakeSession()
        client = MeteoVeoClient(session, CREDS)

        assert await client.async_upload({}, now_iso="2026-08-20 10:00:00") is False
        assert session.requests == []

    @pytest.mark.asyncio
    async def test_rejected_upload_credentials_raise_invalid_credentials(self):
        session = FakeSession(FakeResponse(401, text="INVALIDPASSWORDID"))
        with pytest.raises(InvalidCredentials):
            await MeteoVeoClient(session, CREDS).async_upload(
                {"tempf": 70.0}, now_iso="2026-08-20 10:00:00"
            )

    @pytest.mark.asyncio
    async def test_upload_uses_tls(self):
        session = FakeSession(FakeResponse(200, text="success"))
        await MeteoVeoClient(session, CREDS).async_upload(
            {"tempf": 70.0}, now_iso="2026-08-20 10:00:00"
        )
        _, url, _ = session.requests[0]
        assert url.startswith("https://")
