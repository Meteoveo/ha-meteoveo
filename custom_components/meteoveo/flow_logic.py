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
    API_LANGUAGES,
    CONF_INTEGRATION_KEY,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DEFAULT_API_LANGUAGE,
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


# --- 0.2.0: account-based entries --------------------------------------------

# Where the service has data: mainland Spain with the Balearic Islands, Ceuta
# and Melilla, and the Canary Islands. Deliberately a little wider than the
# service's own box -- the service decides; this only catches an obviously
# wrong pin before an account-side object is created for it.
_SERVICE_AREA = (
    # (south, north, west, east)
    (34.8, 44.5, -10.0, 5.0),
    (27.4, 29.6, -18.5, -13.0),
)


def api_language(ha_language: str | None) -> str:
    """Map Home Assistant's language to one the service writes in."""
    base = (ha_language or "").replace("_", "-").split("-")[0].lower()
    return base if base in API_LANGUAGES else DEFAULT_API_LANGUAGE


def in_service_area(lat: float, lon: float) -> bool:
    """Whether a point is where MeteoVeo has a forecast."""
    return any(s <= lat <= n and w <= lon <= e for s, n, w, e in _SERVICE_AREA)


def looks_like_email(text: str) -> bool:
    """A cheap shape check; the service is the authority on addresses."""
    local, _, domain = text.strip().partition("@")
    return bool(local) and "." in domain and " " not in text.strip()


def same_email(a: str | None, b: str | None) -> bool:
    """Email addresses compared the way people type them."""
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def is_account_entry(data: Mapping[str, Any]) -> bool:
    """Set up by signing in (0.2.0+), as opposed to with a station key only."""
    return bool(data.get(CONF_INTEGRATION_KEY))


def has_station(data: Mapping[str, Any]) -> bool:
    """Whether the entry uploads readings for a station."""
    return bool(data.get(CONF_STATION_ID)) and bool(data.get(CONF_STATION_KEY))


def place_title(place: Mapping[str, Any] | None, fallback: str) -> str:
    """Entry title: the town the service resolved the place to."""
    if place:
        name = place.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback
