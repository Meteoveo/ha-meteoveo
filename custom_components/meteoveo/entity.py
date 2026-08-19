"""Shared entity base.

Everything the station exposes belongs to one device, so it appears as a
single unit in Home Assistant rather than as loose entities.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN
from .coordinator import MeteoVeoCoordinator


class MeteoVeoEntity(CoordinatorEntity[MeteoVeoCoordinator]):
    """Base class tying every entity to the station device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MeteoVeoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        station_id = coordinator.config_entry.data[CONF_STATION_ID]
        # The station id stays stable across key rotations, so entity ids
        # survive re-authentication.
        self._attr_unique_id = f"{station_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station_id)},
            name=self._station.get("name") or station_id,
            manufacturer="MeteoVeo",
            model="Weather station",
            configuration_url="https://www.meteoveo.com/#/cuenta",
        )

    @property
    def _station(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("station", {})

    @property
    def _view(self) -> dict[str, Any]:
        return self.coordinator.data or {}
