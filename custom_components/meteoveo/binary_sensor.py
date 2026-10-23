"""Binary sensors: rain in the next hour, and station health."""

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
from .home import next_hour_attributes

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[BinarySensorEntity] = [RainSoonBinarySensor(runtime.home)]
    if runtime.station is not None:
        entities.append(SensorHealthBinarySensor(runtime.station))
    async_add_entities(entities)


class RainSoonBinarySensor(MeteoVeoEntity, BinarySensorEntity):
    """On when rain is expected at the place within the next hour.

    The ten-minute steps behind the verdict are attributes, so a card or an
    automation can show when it starts, how heavy, and how sure.
    Unavailable outside nowcast coverage, where the service has no next hour.
    """

    entity_description = BinarySensorEntityDescription(
        key="rain_soon",
        translation_key="rain_soon",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rain_soon")

    @property
    def _next_hour(self) -> dict[str, Any] | None:
        value = self._view.get("nextHour")
        return value if isinstance(value, dict) else None

    @property
    def available(self) -> bool:
        return super().available and self._next_hour is not None

    @property
    def is_on(self) -> bool | None:
        next_hour = self._next_hour
        if next_hour is None or not isinstance(next_hour.get("rainSoon"), bool):
            return None
        return next_hour["rainSoon"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        next_hour = self._next_hour
        return next_hour_attributes(next_hour) if next_hour is not None else None


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
