"""HTTP client for the MeteoVeo service.

The client distinguishes two kinds of failure, because Home Assistant treats
them differently. Rejected credentials should lead to a re-authentication
prompt; a service outage should not, or every hiccup would ask the user to
type their station key again.
"""

from __future__ import annotations

from typing import Any, Mapping

import aiohttp

from .auth import Credentials, api_headers, redact, station_token, upload_url_and_params
from .const import (
    API_BASE,
    CLIENT_KIND,
    REQUEST_TIMEOUT_S,
    REVOKE_TIMEOUT_S,
    USER_AGENT,
)


class MeteoVeoError(Exception):
    """Base class for errors raised by this client."""


class InvalidCredentials(MeteoVeoError):
    """The station id or key was rejected."""


class ServiceUnavailable(MeteoVeoError):
    """The service could not answer. Retrying later is the right response."""


class ApiError(MeteoVeoError):
    """The service understood the request and refused it, saying why.

    ``code`` is the service's machine-readable reason (``weak_password``,
    ``invalid_code``, ``invalid_location``, ``too_many_keys`` ...). The message
    holds the status and the code only -- never the request, which may carry
    a password.
    """

    def __init__(self, status: int, code: str | None) -> None:
        super().__init__(f"request refused ({status}): {code or 'no reason given'}")
        self.status = status
        self.code = code


# Rejected credentials. 403 is included because the service also uses it when
# a request arrives without a usable token.
_AUTH_STATUSES = frozenset({401, 403})

# Failures that happen before the service has given a usable answer: DNS, a
# refused or dropped connection, a timeout, a body that is not JSON (a proxy's
# error page, typically). All of them mean "try again later" -- none of them
# says anything about the key.
_TRANSPORT_ERRORS = (aiohttp.ClientError, TimeoutError, ValueError)


class MeteoVeoClient:
    """Reads station data and uploads readings."""

    def __init__(
        self,
        session: Any,
        credentials: Credentials | None = None,
        *,
        integration_key: str | None = None,
    ) -> None:
        self._session = session
        self._credentials = credentials
        self._integration_key = integration_key

    def _safe(self, text: str) -> str:
        """Strip credentials before text goes into an exception or a log."""
        station_key = self._credentials.station_key if self._credentials else ""
        return redact(text, station_key, self._integration_key or "")

    @property
    def _bearer(self) -> str:
        """The integration key when there is one, otherwise the station token.

        Entries set up with only a station key (0.1.x) read the home view with
        the station credential, so they get the forecast as well.
        """
        if self._integration_key:
            return self._integration_key
        if self._credentials is None:
            raise InvalidCredentials("no credential configured")
        return station_token(self._credentials)

    async def async_get_home(
        self, lang: str, etag: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Forecast, next hour and warnings for the configured place.

        Returns ``(None, etag)`` when the service says nothing has changed
        since ``etag``.
        """
        headers = {"If-None-Match": etag} if etag else None
        status, body, response_headers = await _call(
            self._session,
            "GET",
            "/v1/integration/home",
            bearer=self._bearer,
            params={"lang": lang},
            extra_headers=headers,
            accept_not_modified=True,
            secrets=(self._bearer,),
        )
        new_etag = response_headers.get("ETag") or etag
        if status == 304:
            return None, new_etag
        if not isinstance(body, dict):
            raise ServiceUnavailable("home view: unexpected response shape")
        return body, new_etag

    async def async_get_radar(
        self, lang: str, etag: str | None = None
    ) -> tuple[bytes | None, str | None, str]:
        """The radar loop for the configured place (ADR-0833): an animated WEBP.

        Returns ``(None, etag, content_type)`` when nothing changed since ``etag``.
        Outside radar coverage the service refuses with a reason code
        (:class:`ApiError`, e.g. ``no_coverage``).
        """
        status, body, response_headers = await _call(
            self._session,
            "GET",
            "/v1/integration/radar.webp",
            bearer=self._bearer,
            params={"lang": lang},
            extra_headers={"If-None-Match": etag} if etag else None,
            accept_not_modified=True,
            secrets=(self._bearer,),
            binary=True,
        )
        content_type = response_headers.get("Content-Type", "image/webp")
        new_etag = response_headers.get("ETag") or etag
        if status == 304:
            return None, new_etag, content_type
        if not isinstance(body, (bytes, bytearray)) or not body:
            raise ServiceUnavailable("radar: empty response")
        return bytes(body), new_etag, content_type

    async def async_set_location(self, lat: float, lon: float) -> dict[str, Any]:
        """Move the integration key to a new place. Returns the new place."""
        _, body, _ = await _call(
            self._session,
            "PUT",
            "/v1/integration/location",
            bearer=self._bearer,
            payload={"lat": lat, "lon": lon},
            secrets=(self._bearer,),
        )
        place = body.get("place") if isinstance(body, dict) else None
        return place if isinstance(place, dict) else {}

    async def async_revoke_key(self) -> None:
        """Revoke the integration key. Used when the integration is removed."""
        await _call(
            self._session,
            "DELETE",
            "/v1/integration/key",
            bearer=self._bearer,
            timeout=REVOKE_TIMEOUT_S,
            secrets=(self._bearer,),
        )

    def _unreachable(self, what: str, failure: BaseException) -> ServiceUnavailable:
        """An outage error whose message is safe to log.

        aiohttp puts the request URL into its messages, and the upload URL
        carries the key. The caller raises this ``from None`` for the same
        reason: a chained original would print the URL in any traceback.
        """
        detail = self._safe(str(failure)) or type(failure).__name__
        return ServiceUnavailable(f"{what} unreachable: {detail}")

    async def async_get_station(self) -> dict[str, Any]:
        """Station view: position, sensor findings, model verdict, upload state.

        No coordinates are sent. The station's position comes from the service,
        keyed by the token -- sending our own could only ever disagree with it.
        """
        url = f"{API_BASE}/v1/station/self"
        try:
            async with self._session.get(
                url, headers=api_headers(self._credentials)
            ) as response:
                if response.status in _AUTH_STATUSES:
                    raise InvalidCredentials("station id or key was rejected")
                if response.status >= 400:
                    detail = self._safe(await response.text())
                    raise ServiceUnavailable(
                        f"station view unavailable ({response.status}): {detail}"
                    )
                return await response.json()
        except _TRANSPORT_ERRORS as failure:
            raise self._unreachable("station view", failure) from None

    async def async_upload(self, fields: Mapping[str, float], *, now_iso: str) -> bool:
        """Upload one set of readings. Returns False when there was nothing to send.

        An empty upload would still cost a request while telling the service
        nothing, so it is skipped before it is made.
        """
        if not fields:
            return False

        url, params = upload_url_and_params(self._credentials, fields, now_iso=now_iso)
        try:
            async with self._session.get(
                url, params=params, headers={"User-Agent": USER_AGENT}
            ) as response:
                if response.status in _AUTH_STATUSES:
                    raise InvalidCredentials("station id or key was rejected")
                if response.status >= 400:
                    detail = self._safe(await response.text())
                    raise ServiceUnavailable(f"upload failed ({response.status}): {detail}")
                return True
        except _TRANSPORT_ERRORS as failure:
            raise self._unreachable("upload", failure) from None


class AccountClient:
    """Account requests made while a setup or options flow is open.

    These take the account's session token, which is used for the length of
    one flow and then dropped: nothing in this class stores it.
    """

    def __init__(self, session: Any) -> None:
        self._session = session

    async def async_signup(
        self, email: str, password: str, *, marketing: bool, lang: str
    ) -> None:
        """Start a sign-up; the service emails a confirmation code."""
        await _call(
            self._session,
            "POST",
            "/auth/signup",
            payload={
                "email": email,
                "password": password,
                "marketingConsent": marketing,
                "lang": lang,
            },
            secrets=(password,),
        )

    async def async_verify(self, email: str, code: str) -> None:
        """Confirm the emailed code."""
        await _call(
            self._session,
            "POST",
            "/auth/signup/verify",
            payload={"email": email, "code": code},
        )

    async def async_login(self, email: str, password: str) -> str:
        """Sign in. Returns the session token."""
        _, body, _ = await _call(
            self._session,
            "POST",
            "/auth/login/password",
            payload={"email": email, "password": password},
            secrets=(password,),
        )
        token = body.get("token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise ServiceUnavailable("sign-in answered without a session")
        return token

    async def async_create_station(
        self, token: str, *, name: str, lat: float, lon: float, sensor_height_cm: int
    ) -> dict[str, Any]:
        """Create a directly connected station: ``{stationId, ingestId, secret}``."""
        _, body, _ = await _call(
            self._session,
            "POST",
            "/v1/me/stations/direct",
            bearer=token,
            payload={
                "name": name,
                "lat": lat,
                "lon": lon,
                "sensorHeightCm": sensor_height_cm,
            },
            secrets=(token,),
        )
        return _require(body, "stationId", "ingestId", "secret")

    async def async_renew_ingest_key(self, token: str, station_ref: int) -> dict[str, Any]:
        """Issue a new upload key for a station: ``{ingestId?, secret}``."""
        _, body, _ = await _call(
            self._session,
            "POST",
            f"/v1/me/stations/{int(station_ref)}/ingest-key",
            bearer=token,
            secrets=(token,),
        )
        return _require(body, "secret")

    async def async_create_integration_key(
        self,
        token: str,
        *,
        lat: float,
        lon: float,
        label: str | None,
        station_ref: int | None,
    ) -> dict[str, Any]:
        """Issue an integration key: ``{keyId, key, place}``."""
        payload: dict[str, Any] = {"clientKind": CLIENT_KIND, "lat": lat, "lon": lon}
        if label:
            payload["label"] = label[:80]
        if station_ref is not None:
            payload["stationId"] = station_ref
        _, body, _ = await _call(
            self._session,
            "POST",
            "/v1/me/integration-keys",
            bearer=token,
            payload=payload,
            secrets=(token,),
        )
        return _require(body, "keyId", "key")

    async def async_delete_integration_key(self, token: str, key_id: str) -> None:
        """Revoke one of the account's integration keys (204 even if unknown)."""
        await _call(
            self._session,
            "DELETE",
            f"/v1/me/integration-keys/{key_id}",
            bearer=token,
            secrets=(token,),
        )

    async def async_delete_account(self, token: str, *, password: str, confirm: str) -> None:
        """Delete the account. Irreversible."""
        await _call(
            self._session,
            "POST",
            "/v1/me/delete",
            bearer=token,
            payload={"password": password, "confirm": confirm},
            secrets=(token, password),
        )


def _require(body: Any, *fields: str) -> dict[str, Any]:
    """A success response must carry what the next step depends on."""
    if not isinstance(body, dict) or any(body.get(field) in (None, "") for field in fields):
        raise ServiceUnavailable("unexpected response shape")
    return body


def _error_code(body: Any) -> str | None:
    """The service's reason: ``{"error": {"code": ...}}`` or ``{"error": "..."}``."""
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return None


async def _call(
    session: Any,
    method: str,
    path: str,
    *,
    bearer: str | None = None,
    payload: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = REQUEST_TIMEOUT_S,
    accept_not_modified: bool = False,
    secrets: tuple[str, ...] = (),
    binary: bool = False,
) -> tuple[int, Any, Mapping[str, str]]:
    """One request, with failures sorted into the three kinds the flows need.

    * 401, or 403 without a reason -> :class:`InvalidCredentials`
    * a refusal with a reason code -> :class:`ApiError`
    * everything else that is not a success (network, timeout, 429, 5xx, an
      unexpected 4xx, a body that is not JSON) -> :class:`ServiceUnavailable`

    No message raised here contains the request body or a credential.
    """
    headers = {"Accept": "image/*" if binary else "application/json", "User-Agent": USER_AGENT}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if extra_headers:
        headers.update(extra_headers)
    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=timeout),
    }
    if payload is not None:
        kwargs["json"] = payload
    if params is not None:
        kwargs["params"] = params

    try:
        async with session.request(method, f"{API_BASE}{path}", **kwargs) as response:
            status = response.status
            response_headers = getattr(response, "headers", None) or {}
            if status == 304 and accept_not_modified:
                return status, None, response_headers
            if status == 204:
                return status, None, response_headers
            if 400 <= status < 500 and status != 429:
                try:
                    body = await response.json(content_type=None)
                except _TRANSPORT_ERRORS:
                    body = None
                code = _error_code(body)
                if status == 401 or (status == 403 and code is None):
                    raise InvalidCredentials(f"{method} {path}: rejected ({status})")
                if code is not None:
                    raise ApiError(status, code)
                raise ServiceUnavailable(f"{method} {path}: unexpected status {status}")
            if status >= 400:
                raise ServiceUnavailable(f"{method} {path}: service answered {status}")
            body = await response.read() if binary else await response.json(content_type=None)
            return status, body, response_headers
    except _TRANSPORT_ERRORS as failure:
        detail = redact(str(failure), *secrets) or type(failure).__name__
        raise ServiceUnavailable(f"{method} {path} unreachable: {detail}") from None
