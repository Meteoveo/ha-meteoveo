"""The MeteoVeo integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .auth import Credentials
from .card import async_register_card
from .client import InvalidCredentials, MeteoVeoClient
from .const import (
    CONF_INTEGRATION_KEY,
    CONF_MEASUREMENTS,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DEFAULT_UPLOAD_INTERVAL_S,
    DOMAIN,
)
from .coordinator import (
    HomeCoordinator,
    MeteoVeoConfigEntry,
    MeteoVeoCoordinator,
    MeteoVeoData,
)
from .entity import base_id_for, device_info_for
from .flow_logic import api_language, has_station, is_account_entry
from .uploader import upload_once

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.WEATHER,
    Platform.EVENT,
    Platform.IMAGE,
]

#: Plus only, and created from the service's answer rather than up front
#: (ADR-0866 D6): the radar playback camera and its window. Forwarded for
#: every account entry, because an account can reach Plus while Home
#: Assistant runs and the entities must be able to appear without a restart.
PLUS_PLATFORMS: list[Platform] = [Platform.CAMERA, Platform.SELECT]


def platforms_for(entry: MeteoVeoConfigEntry) -> list[Platform]:
    """Which platforms this entry needs.

    A 0.1.x station-key entry has no account behind it and so can never
    reach Plus; setting up the camera and select components for it would
    load them for an entry that will never have one of their entities.
    """
    if is_account_entry(entry.data):
        return PLATFORMS + PLUS_PLATFORMS
    return PLATFORMS

# Set up through the UI only; there is no YAML configuration.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Once per Home Assistant start: serve the bundled card."""
    await async_register_card(hass)
    return True


def _client_for(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> MeteoVeoClient:
    credentials = (
        Credentials(
            station_id=entry.data[CONF_STATION_ID],
            station_key=entry.data[CONF_STATION_KEY],
        )
        if has_station(entry.data)
        else None
    )
    return MeteoVeoClient(
        async_get_clientsession(hass),
        credentials,
        integration_key=entry.data.get(CONF_INTEGRATION_KEY),
    )


async def async_setup_entry(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> bool:
    """Set up MeteoVeo from a config entry."""
    client = _client_for(hass, entry)
    account = is_account_entry(entry.data)
    home = HomeCoordinator(
        hass,
        entry,
        client,
        lang=api_language(hass.config.language),
        owns_auth=account,
    )
    station = MeteoVeoCoordinator(hass, entry, client) if has_station(entry.data) else None

    # The coordinator that speaks for the entry's credential must succeed:
    # an entry that loads and then produces nothing but errors is harder to
    # diagnose than one that refuses to start and says why. A rejected
    # credential raises ConfigEntryAuthFailed, which opens re-authentication.
    #
    # The other one is allowed to fail on its own: a forecast outage must
    # not stop a station from uploading, and a station-view outage must not
    # take the forecast away. Its entities are unavailable until it recovers.
    primary, secondary = (home, station) if account else (station, home)
    assert primary is not None
    await primary.async_config_entry_first_refresh()
    if secondary is not None:
        await secondary.async_refresh()

    base_id = base_id_for(entry)
    entry.runtime_data = MeteoVeoData(
        client=client,
        home=home,
        station=station,
        base_id=base_id,
        device_info=device_info_for(
            entry,
            base_id,
            station_view=station.data if station else None,
            home=home.data,
        ),
    )
    await hass.config_entries.async_forward_entry_setups(entry, platforms_for(entry))
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_change))

    if station is not None:
        _start_uploads(hass, entry, client)
    return True


def _start_uploads(
    hass: HomeAssistant, entry: MeteoVeoConfigEntry, client: MeteoVeoClient
) -> None:
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


async def async_unload_entry(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, platforms_for(entry))


async def async_remove_entry(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> None:
    """Revoke the integration key when the integration is deleted.

    Only the key: the account, any station and its readings stay. Best effort
    with a short timeout -- removal never fails or hangs because the service
    cannot be reached; an unused key is visible as such on the service side.
    Entries set up with a station key only have nothing to revoke.
    """
    if not is_account_entry(entry.data):
        return
    client = MeteoVeoClient(
        async_get_clientsession(hass),
        integration_key=entry.data[CONF_INTEGRATION_KEY],
    )
    try:
        await client.async_revoke_key()
    except Exception as failure:  # noqa: BLE001 - removal must never fail
        _LOGGER.debug("could not revoke the integration key: %s", type(failure).__name__)


async def _async_reload_on_change(
    hass: HomeAssistant, entry: MeteoVeoConfigEntry
) -> None:
    """Re-read the configuration after the options or the place changed."""
    await hass.config_entries.async_reload(entry.entry_id)
