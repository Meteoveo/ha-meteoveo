"""Sensors describing the station itself."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MeteoVeoConfigEntry
from .entity import MeteoVeoEntity

# Everything comes from a single coordinator refresh, so there is nothing to
# parallelise and nothing to throttle.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BestModelSensor(coordinator),
            AcceptedUploadsSensor(coordinator),
            LastUploadSensor(coordinator),
        ]
    )


class BestModelSensor(MeteoVeoEntity, SensorEntity):
    """Which forecast model performs best at this station.

    While there is not enough history to tell, the state says so and the
    attributes count down the days -- an empty value would look like a fault.
    """

    entity_description = SensorEntityDescription(
        key="best_model",
        translation_key="best_model",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "best_model")

    @property
    def native_value(self) -> str | None:
        model = self._view.get("model", {})
        if model.get("status") == "ready":
            return model.get("model")
        return "collecting"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        model = self._view.get("model", {})
        if model.get("status") == "ready":
            return {
                "mean_absolute_error": model.get("mae"),
                "bias": model.get("bias"),
                "samples": model.get("samples"),
            }
        return {
            "samples": model.get("samples", 0),
            "samples_needed": model.get("samplesNeeded"),
            "days_remaining": model.get("daysRemaining"),
        }


class AcceptedUploadsSensor(MeteoVeoEntity, SensorEntity):
    """How many readings the service has accepted."""

    entity_description = SensorEntityDescription(
        key="accepted_uploads",
        translation_key="accepted_uploads",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class="total_increasing",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "accepted_uploads")

    @property
    def native_value(self) -> int | None:
        return self._view.get("upload", {}).get("acceptedCount")


class LastUploadSensor(MeteoVeoEntity, SensorEntity):
    """When the service last accepted a reading."""

    entity_description = SensorEntityDescription(
        key="last_upload",
        translation_key="last_upload",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class="timestamp",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "last_upload")

    @property
    def native_value(self):
        from homeassistant.util import dt as dt_util

        raw = self._view.get("upload", {}).get("lastSeenAt")
        return dt_util.parse_datetime(raw) if raw else None
