"""Diagnostics download.

People attach this file to public bug reports, so everything that could
identify or authenticate them is redacted: keys, the station id, the email
address and the coordinates of their home.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EMAIL,
    CONF_INTEGRATION_KEY,
    CONF_KEY_ID,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_REF,
)
from .coordinator import MeteoVeoConfigEntry

TO_REDACT = {
    CONF_INTEGRATION_KEY,
    CONF_KEY_ID,
    CONF_EMAIL,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_REF,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    # Inside the service's responses.
    "lat",
    "lon",
    "name",
    "ingestId",
    "secret",
    "token",
    "key",
    "keyId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MeteoVeoConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    runtime = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "home": {
            "last_update_success": runtime.home.last_update_success,
            "data": async_redact_data(runtime.home.data or {}, TO_REDACT),
        },
        "station": (
            None
            if runtime.station is None
            else {
                "last_update_success": runtime.station.last_update_success,
                "data": async_redact_data(runtime.station.data or {}, TO_REDACT),
            }
        ),
    }
