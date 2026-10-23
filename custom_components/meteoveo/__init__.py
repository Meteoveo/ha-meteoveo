"""The MeteoVeo integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .auth import Credentials
from .client import InvalidCredentials, MeteoVeoClient
from .const import (
    CONF_MEASUREMENTS,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DEFAULT_UPLOAD_INTERVAL_S,
)
from .coordinator import MeteoVeoConfigEntry, MeteoVeoCoordinator
from .uploader import upload_once

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> bool:
    """Set up MeteoVeo from a config entry."""
    credentials = Credentials(
        station_id=entry.data[CONF_STATION_ID],
        station_key=entry.data[CONF_STATION_KEY],
    )
    client = MeteoVeoClient(async_get_clientsession(hass), credentials)
    coordinator = MeteoVeoCoordinator(hass, entry, client)

    # Fail here rather than later: an entry that loads and then produces
    # nothing but errors is harder to diagnose than one that refuses to start
    # and says why. A rejected key raises ConfigEntryAuthFailed from the
    # coordinator, which opens the re-authentication flow.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options_change))

    # Uploads run on a timer rather than on every state change: a station
    # reporting several sensors would otherwise fire a burst of requests
    # carrying almost the same reading.
    async def _upload(_now) -> None:
        selection = entry.options.get(CONF_MEASUREMENTS, {})
        if not selection:
            return
        try:
            await upload_once(
                client,
                hass.states,
                selection,
                now_iso=dt_util.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
        except InvalidCredentials:
            # This timer is not the coordinator: an exception left to escape
            # here would only reach the log, once a minute, and never ask for
            # a new key. Home Assistant opens at most one re-authentication
            # flow per entry, so a key that stays rejected does not stack up
            # prompts.
            entry.async_start_reauth(hass)

    entry.async_on_unload(
        async_track_time_interval(
            hass, _upload, timedelta(seconds=DEFAULT_UPLOAD_INTERVAL_S)
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_options_change(
    hass: HomeAssistant, entry: MeteoVeoConfigEntry
) -> None:
    """Re-read the measurement mapping after it is changed in the options."""
    await hass.config_entries.async_reload(entry.entry_id)
