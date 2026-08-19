"""Binary sensors for station health."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MeteoVeoConfigEntry
from .entity import MeteoVeoEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([SensorHealthBinarySensor(entry.runtime_data)])


class SensorHealthBinarySensor(MeteoVeoEntity, BinarySensorEntity):
    """On when the service has flagged something about this station's sensors.

    The findings are listed as an attribute, so an automation can react to a
    specific one rather than only to "something is wrong".
    """

    entity_description = BinarySensorEntityDescription(
        key="sensor_problem",
        translation_key="sensor_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sensor_problem")

    @property
    def is_on(self) -> bool:
        return bool(self._findings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"findings": self._findings}

    @property
    def _findings(self) -> list[str]:
        return self._view.get("health", {}).get("findings", []) or []
