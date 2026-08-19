"""HTTP client for the MeteoVeo service.

The client distinguishes two kinds of failure, because Home Assistant treats
them differently. Rejected credentials should lead to a re-authentication
prompt; a service outage should not, or every hiccup would ask the user to
type their station key again.
"""

from __future__ import annotations

from typing import Any, Mapping

from .auth import Credentials, api_headers, redact, upload_url_and_params
from .const import API_BASE


class MeteoVeoError(Exception):
    """Base class for errors raised by this client."""


class InvalidCredentials(MeteoVeoError):
    """The station id or key was rejected."""


class ServiceUnavailable(MeteoVeoError):
    """The service could not answer. Retrying later is the right response."""


# Rejected credentials. 403 is included because the service also uses it when
# a request arrives without a usable token.
_AUTH_STATUSES = frozenset({401, 403})


class MeteoVeoClient:
    """Reads station data and uploads readings."""

    def __init__(self, session: Any, credentials: Credentials) -> None:
        self._session = session
        self._credentials = credentials

    def _safe(self, text: str) -> str:
        """Strip credentials before text goes into an exception or a log."""
        return redact(text, self._credentials.station_key)

    async def async_get_station(self) -> dict[str, Any]:
        """Station view: position, sensor findings, model verdict, upload state.

        No coordinates are sent. The station's position comes from the service,
        keyed by the token -- sending our own could only ever disagree with it.
        """
        url = f"{API_BASE}/v1/station/self"
        async with self._session.get(url, headers=api_headers(self._credentials)) as response:
            if response.status in _AUTH_STATUSES:
                raise InvalidCredentials("station id or key was rejected")
            if response.status >= 400:
                detail = self._safe(await response.text())
                raise ServiceUnavailable(f"station view unavailable ({response.status}): {detail}")
            return await response.json()

    async def async_upload(self, fields: Mapping[str, float], *, now_iso: str) -> bool:
        """Upload one set of readings. Returns False when there was nothing to send.

        An empty upload would still cost a request while telling the service
        nothing, so it is skipped before it is made.
        """
        if not fields:
            return False

        url, params = upload_url_and_params(self._credentials, fields, now_iso=now_iso)
        async with self._session.get(url, params=params) as response:
            if response.status in _AUTH_STATUSES:
                raise InvalidCredentials("station id or key was rejected")
            if response.status >= 400:
                detail = self._safe(await response.text())
                raise ServiceUnavailable(f"upload failed ({response.status}): {detail}")
            return True
