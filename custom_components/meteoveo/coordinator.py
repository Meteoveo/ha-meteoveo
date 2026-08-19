"""Polling and upload scheduling."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import InvalidCredentials, MeteoVeoClient, ServiceUnavailable

_LOGGER = logging.getLogger(__name__)

# The station view changes when a reading arrives or a daily score is written.
# Five minutes keeps it current without polling a service that cannot change
# faster than its inputs.
UPDATE_INTERVAL = timedelta(minutes=5)

type MeteoVeoConfigEntry = ConfigEntry[MeteoVeoCoordinator]


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
