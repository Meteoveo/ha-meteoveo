"""Polling and upload scheduling.

An entry has up to two coordinators:

* :class:`HomeCoordinator` -- every entry. The forecast, the next hour and the
  weather warnings for the entry's place.
* :class:`MeteoVeoCoordinator` -- entries with a station. The station view:
  sensor findings, upload state, the best-model verdict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import InvalidCredentials, MeteoVeoClient, ServiceUnavailable
from .const import HOME_UPDATE_INTERVAL_S

_LOGGER = logging.getLogger(__name__)

# The station view changes when a reading arrives or a daily score is written.
# Five minutes keeps it current without polling a service that cannot change
# faster than its inputs.
UPDATE_INTERVAL = timedelta(minutes=5)

# The service asks not to be polled more often than this; the nowcast behind
# the next-hour view is itself recomputed every few minutes.
HOME_UPDATE_INTERVAL = timedelta(seconds=HOME_UPDATE_INTERVAL_S)


@dataclass
class MeteoVeoData:
    """What a loaded entry keeps at hand."""

    client: MeteoVeoClient
    home: HomeCoordinator
    station: MeteoVeoCoordinator | None
    #: Prefix of every entity's unique id and the device identifier. Stable
    #: across re-authentication, so entity history is never orphaned.
    base_id: str
    device_info: DeviceInfo


type MeteoVeoConfigEntry = ConfigEntry[MeteoVeoData]


class MeteoVeoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keeps the station view current."""

    config_entry: MeteoVeoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MeteoVeoConfigEntry,
        client: MeteoVeoClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="MeteoVeo station",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_station()
        except InvalidCredentials as failure:
            # Raising this rather than UpdateFailed is what starts the
            # re-authentication flow instead of retrying forever with a key
            # that has been replaced.
            raise ConfigEntryAuthFailed("station key was rejected") from failure
        except ServiceUnavailable as failure:
            # The coordinator logs the first failure and stays quiet until the
            # service recovers, so an outage does not fill the log.
            raise UpdateFailed(str(failure)) from failure


class HomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keeps the forecast for the entry's place current.

    Conditional requests: the service answers 304 when nothing changed, and
    the previous data is kept.
    """

    config_entry: MeteoVeoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MeteoVeoConfigEntry,
        client: MeteoVeoClient,
        *,
        lang: str,
        owns_auth: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="MeteoVeo forecast",
            update_interval=HOME_UPDATE_INTERVAL,
        )
        self.client = client
        self._lang = lang
        # Whether a rejected credential here means "ask for a new one". For
        # an entry set up with a station key only, the station view is what
        # decides that: a forecast refusal must not make a working station
        # stop uploading while its owner is asked to retype a valid key.
        self._owns_auth = owns_auth
        self._etag: str | None = None

    @property
    def lang(self) -> str:
        """The language the home view (and the radar loop) is asked in."""
        return self._lang

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data, etag = await self.client.async_get_home(
                self._lang, etag=self._etag if self.data else None
            )
        except InvalidCredentials as failure:
            if self._owns_auth:
                raise ConfigEntryAuthFailed("integration key was rejected") from failure
            raise UpdateFailed("forecast refused for this station key") from failure
        except ServiceUnavailable as failure:
            raise UpdateFailed(str(failure)) from failure

        self._etag = etag
        if data is None:
            # 304 Not Modified.
            return self.data
        return data
