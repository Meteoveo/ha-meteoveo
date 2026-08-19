"""Setup logic, kept out of the Home Assistant flow class so it can be tested
without a running Home Assistant.

What the setup screen does with a failure decides whether someone can recover
from it. A mistyped key and a service outage must not produce the same
message: the first is fixed by retyping, the second by waiting -- and telling
someone their key is wrong while the service is merely down sends them off to
generate a new one, which would stop the station that is already using it.
"""

from __future__ import annotations

from typing import Any, Mapping

from .client import InvalidCredentials, ServiceUnavailable
from .const import (
    DEFAULT_UPLOAD_INTERVAL_S,
    MAX_UPLOAD_INTERVAL_S,
    MIN_UPLOAD_INTERVAL_S,
)

#: Error keys shown by the config flow; each maps to a translated message.
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UNKNOWN = "unknown"


def clean_station_id(typed: str) -> str:
    """Normalise a pasted station id.

    People copy this from a web page, so stray whitespace and lower case are
    routine. An empty result is left empty -- deciding what to do about a
    blank field belongs to the flow, not here.
    """
    return typed.strip().upper()


def error_for(failure: BaseException) -> str:
    """Map an exception to the error key the setup screen should show."""
    if isinstance(failure, InvalidCredentials):
        return ERROR_INVALID_AUTH
    if isinstance(failure, ServiceUnavailable):
        return ERROR_CANNOT_CONNECT
    # Anything unforeseen is reported as unknown rather than as a credential
    # problem: sending someone to rotate a working key is worse than telling
    # them something went wrong.
    return ERROR_UNKNOWN


def unique_id_for(station_id: str) -> str:
    """Stable identity for a configured station.

    Keyed on the station id rather than the key, so rotating a key does not
    create a duplicate entry -- and adding the same station twice is caught.
    """
    return station_id.strip().lower()


def entry_title(view: Mapping[str, Any] | None, station_id: str) -> str:
    """Human-readable name for the config entry.

    Falls back to the station id: an entry with no name would be
    unidentifiable in the device list.
    """
    if view:
        station = view.get("station")
        if isinstance(station, Mapping):
            name = station.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return station_id


def clamp_upload_interval(value: Any) -> int:
    """Keep the upload interval inside the range the service expects.

    Out-of-range values are brought back rather than rejected: a value stored
    by an older version must still load, and refusing to start over a setting
    would be worse than correcting it.
    """
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_UPLOAD_INTERVAL_S
    if seconds <= 0:
        return DEFAULT_UPLOAD_INTERVAL_S
    return max(MIN_UPLOAD_INTERVAL_S, min(MAX_UPLOAD_INTERVAL_S, seconds))
