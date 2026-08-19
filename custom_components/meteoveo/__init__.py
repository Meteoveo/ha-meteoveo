"""The MeteoVeo integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import Credentials
from .client import MeteoVeoClient
from .const import CONF_STATION_ID, CONF_STATION_KEY
from .coordinator import MeteoVeoConfigEntry, MeteoVeoCoordinator

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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MeteoVeoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_options_change(
    hass: HomeAssistant, entry: MeteoVeoConfigEntry
) -> None:
    """Re-read the measurement mapping after it is changed in the options."""
    await hass.config_entries.async_reload(entry.entry_id)
