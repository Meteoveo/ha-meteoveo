"""Shared entity base.

Everything an entry exposes belongs to one device, so it appears as a single
unit in Home Assistant rather than as loose entities. The device is named
after the user's own station (station-key entries) or after the town the
service resolved the place to -- never after anyone else's station.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import CONF_STATION_ID, DOMAIN
from .coordinator import MeteoVeoConfigEntry
from .flow_logic import is_account_entry

CONFIGURATION_URL = "https://www.meteoveo.com/#/account"


def base_id_for(entry: MeteoVeoConfigEntry) -> str:
    """Prefix of every unique id in an entry.

    Station-key entries keep the station id, as in 0.1.x, so upgrading does
    not orphan entity history. Account entries use the entry's unique id (the
    first integration key's id), which is kept when re-authentication issues
    a new key.
    """
    if is_account_entry(entry.data):
        return entry.unique_id or entry.entry_id
    return entry.data[CONF_STATION_ID]


def device_info_for(
    entry: MeteoVeoConfigEntry,
    base_id: str,
    *,
    station_view: dict[str, Any] | None,
    home: dict[str, Any] | None,
) -> DeviceInfo:
    """The one device every entity of an entry belongs to."""
    if is_account_entry(entry.data):
        place = (home or {}).get("place") or {}
        # The brand leads (owner, 2026-10-23): "MeteoVeo Almiserà" makes every
        # entity ID say where it comes from (weather.meteoveo_almisera), on the
        # dashboard and in automations alike. Users can still rename it.
        name = f"MeteoVeo {place.get('name') or entry.title}"
        model = "Forecast"
    else:
        station = (station_view or {}).get("station") or {}
        name = station.get("name") or base_id
        model = "Weather station"
    return DeviceInfo(
        identifiers={(DOMAIN, base_id)},
        name=name,
        manufacturer="MeteoVeo",
        model=model,
        configuration_url=CONFIGURATION_URL,
    )


class MeteoVeoEntity(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]):
    """Base class tying every entity to the entry's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator[dict[str, Any]], key: str) -> None:
        super().__init__(coordinator)
        runtime = coordinator.config_entry.runtime_data
        self._attr_unique_id = f"{runtime.base_id}_{key}"
        self._attr_device_info = runtime.device_info

    @property
    def _station(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("station", {})

    @property
    def _view(self) -> dict[str, Any]:
        return self.coordinator.data or {}
