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
from homeassistant.util import dt as dt_util

from .coordinator import MeteoVeoConfigEntry
from .entity import MeteoVeoEntity, add_when_allowed
from .home import (
    WARNING_LEVELS,
    active_levels,
    lightning_attributes,
    lightning_nearby,
    lightning_unlocked,
    next_hour_attributes,
    warnings_list,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[BinarySensorEntity] = [RainSoonBinarySensor(runtime.home)]
    entities += [WarningLevelBinarySensor(runtime.home, level) for level in WARNING_LEVELS]
    if runtime.station is not None:
        entities.append(SensorHealthBinarySensor(runtime.station))
    async_add_entities(entities)

    add_when_allowed(
        hass,
        entry,
        async_add_entities,
        platform="binary_sensor",
        unique_id=f"{runtime.base_id}_lightning_nearby",
        allowed=lightning_unlocked,
        build=lambda: [LightningNearbyBinarySensor(runtime.home)],
    )


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


class WarningLevelBinarySensor(MeteoVeoEntity, BinarySensorEntity):
    """On while an official warning of this level is in force at the place.

    One per level, so an automation can react to "orange or worse" without
    templates. The warnings of this level that are in force are attributes.
    """

    def __init__(self, coordinator, level: str) -> None:
        super().__init__(coordinator, f"warning_{level}")
        self.entity_description = BinarySensorEntityDescription(
            key=f"warning_{level}",
            translation_key=f"warning_{level}",
            device_class=BinarySensorDeviceClass.SAFETY,
        )
        self._level = level

    @property
    def is_on(self) -> bool | None:
        warnings = warnings_list(self._view)
        if warnings is None:
            return None
        return self._level in active_levels(warnings, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        return {
            "warnings": [
                w
                for w in warnings_list(self._view) or []
                if w.get("level") == self._level and self._level in active_levels([w], now)
            ]
        }


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


class LightningNearbyBinarySensor(MeteoVeoEntity, BinarySensorEntity):
    """On while a strike has been counted within 30 km of the place.

    The counts at 15, 30 and 50 km, the nearest strike and its bearing are
    attributes, so an automation can react to "within 15 km" without a
    second entity. Created only once the account may see the data, and
    unavailable if that right is later lost (ADR-0866 D5).
    """

    entity_description = BinarySensorEntityDescription(
        key="lightning_nearby",
        translation_key="lightning_nearby",
        device_class=BinarySensorDeviceClass.SAFETY,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "lightning_nearby")

    @property
    def available(self) -> bool:
        return super().available and lightning_unlocked(self._view)

    @property
    def is_on(self) -> bool | None:
        return lightning_nearby(self._view)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return lightning_attributes(self._view)
