"""Sensors: rain start and end, weather warnings, and the station itself."""

from __future__ import annotations

from typing import Any

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UV_INDEX, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MeteoVeoConfigEntry
from .entity import MeteoVeoEntity
from .home import (
    RAIN_BANDS,
    current_hour,
    dew_point,
    highest_level,
    minutes_to_rain,
    next_warning_onset,
    parse_time,
    rain_intensity_now,
    uv_max_today,
    warnings_list,
)

# Everything comes from a single coordinator refresh, so there is nothing to
# parallelise and nothing to throttle.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [
        RainTimeSensor(runtime.home, "rain_start", "rainStartsAt"),
        RainTimeSensor(runtime.home, "rain_end", "rainEndsAt"),
        WarningsSensor(runtime.home),
        NextWarningSensor(runtime.home),
        FeelsLikeSensor(runtime.home),
        DewPointSensor(runtime.home),
        UvIndexSensor(runtime.home),
        UvMaxTodaySensor(runtime.home),
        MinutesToRainSensor(runtime.home),
        RainIntensitySensor(runtime.home),
    ]
    coordinator = runtime.station
    if coordinator is not None:
        entities += [
            BestModelSensor(coordinator),
            AcceptedUploadsSensor(coordinator),
            LastUploadSensor(coordinator),
            GraceRemainingSensor(coordinator),
        ]
    async_add_entities(entities)


class RainTimeSensor(MeteoVeoEntity, SensorEntity):
    """When the next rain starts, or when the current rain ends.

    Unknown when there is nothing to report (no rain coming, or not raining
    now); unavailable outside nowcast coverage.
    """

    def __init__(self, coordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self.entity_description = SensorEntityDescription(
            key=key,
            translation_key=key,
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        self._field = field

    @property
    def _next_hour(self) -> dict[str, Any] | None:
        value = self._view.get("nextHour")
        return value if isinstance(value, dict) else None

    @property
    def available(self) -> bool:
        return super().available and self._next_hour is not None

    @property
    def native_value(self) -> datetime | None:
        return parse_time((self._next_hour or {}).get(self._field))


class WarningsSensor(MeteoVeoEntity, SensorEntity):
    """How many official weather warnings are active for the place.

    The warnings themselves, and the highest level among them, are
    attributes. Headlines are the issuing agency's own text.
    """

    entity_description = SensorEntityDescription(
        key="warnings",
        translation_key="warnings",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "warnings")

    @property
    def native_value(self) -> int | None:
        warnings = warnings_list(self._view)
        return None if warnings is None else len(warnings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        warnings = warnings_list(self._view) or []
        return {"highest_level": highest_level(warnings), "warnings": warnings}


class NextWarningSensor(MeteoVeoEntity, SensorEntity):
    """When the next official warning that has not started yet begins."""

    entity_description = SensorEntityDescription(
        key="next_warning",
        translation_key="next_warning",
        device_class=SensorDeviceClass.TIMESTAMP,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "next_warning")

    @property
    def native_value(self) -> datetime | None:
        return next_warning_onset(warnings_list(self._view), dt_util.utcnow())


class FeelsLikeSensor(MeteoVeoEntity, SensorEntity):
    """The apparent temperature of the current hour."""

    entity_description = SensorEntityDescription(
        key="apparent_temperature",
        translation_key="apparent_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class="measurement",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "apparent_temperature")

    @property
    def native_value(self) -> float | None:
        return (current_hour(self._view, dt_util.utcnow()) or {}).get("feelsLikeC")


class DewPointSensor(MeteoVeoEntity, SensorEntity):
    """The dew point, from the current temperature and humidity."""

    entity_description = SensorEntityDescription(
        key="dew_point",
        translation_key="dew_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class="measurement",
        suggested_display_precision=1,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "dew_point")

    @property
    def native_value(self) -> float | None:
        current = self._view.get("current") or {}
        return dew_point(current.get("tempC"), current.get("humidityPct"))


class UvIndexSensor(MeteoVeoEntity, SensorEntity):
    """The UV index forecast for the current hour."""

    entity_description = SensorEntityDescription(
        key="uv_index",
        translation_key="uv_index",
        native_unit_of_measurement=UV_INDEX,
        state_class="measurement",
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "uv_index")

    @property
    def native_value(self) -> float | None:
        return (current_hour(self._view, dt_util.utcnow()) or {}).get("uvIndex")


class UvMaxTodaySensor(MeteoVeoEntity, SensorEntity):
    """Today's highest UV index."""

    entity_description = SensorEntityDescription(
        key="uv_index_max_today",
        translation_key="uv_index_max_today",
        native_unit_of_measurement=UV_INDEX,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "uv_index_max_today")

    @property
    def native_value(self) -> float | None:
        return uv_max_today(self._view, dt_util.utcnow())


class _NextHourSensor(MeteoVeoEntity, SensorEntity):
    """A value read from the next hour; unavailable outside nowcast coverage."""

    @property
    def _next_hour(self) -> dict[str, Any] | None:
        value = self._view.get("nextHour")
        return value if isinstance(value, dict) else None

    @property
    def available(self) -> bool:
        return super().available and self._next_hour is not None


class MinutesToRainSensor(_NextHourSensor):
    """Minutes until it rains: 0 while raining, unknown when none is expected.

    A number, so a numeric-state trigger ("below 30") works without templates.
    """

    entity_description = SensorEntityDescription(
        key="minutes_to_rain",
        translation_key="minutes_to_rain",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "minutes_to_rain")

    @property
    def native_value(self) -> int | None:
        return minutes_to_rain(self._next_hour, dt_util.utcnow())


class RainIntensitySensor(_NextHourSensor):
    """How hard it rains now, from the nowcast step covering now."""

    entity_description = SensorEntityDescription(
        key="rain_intensity_now",
        translation_key="rain_intensity_now",
        device_class=SensorDeviceClass.ENUM,
        options=list(RAIN_BANDS),
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rain_intensity_now")

    @property
    def native_value(self) -> str | None:
        return rain_intensity_now(self._next_hour, dt_util.utcnow())


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
        if model.get("status") == "paused":
            # The station has been silent past the grace window. The verdict
            # is station-specific, so it pauses; the forecast does not.
            return "paused"
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
        if model.get("status") == "paused":
            return {
                "hours_silent": model.get("hoursSilent"),
                "grace_hours": model.get("graceHours"),
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


class GraceRemainingSensor(MeteoVeoEntity, SensorEntity):
    """Hours left before the station-specific extras pause, if it stays silent.

    The forecast itself is always available. What a silent station loses
    after the grace window are the extras computed from its own readings --
    today the best-model verdict. This sensor makes the remaining margin
    visible *before* it runs out, so an automation can warn about a station
    that stopped sending.
    """

    entity_description = SensorEntityDescription(
        key="grace_remaining",
        translation_key="grace_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="h",
        state_class="measurement",
        suggested_display_precision=1,
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "grace_remaining")

    @property
    def native_value(self) -> float | None:
        reciprocity = self._view.get("reciprocity")
        if not reciprocity:
            return None
        return round(float(reciprocity.get("hoursRemaining", 0)), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        reciprocity = self._view.get("reciprocity") or {}
        return {
            "derived_data_available": reciprocity.get("allowed"),
            "hours_silent": reciprocity.get("hoursSilent"),
            "grace_hours": reciprocity.get("graceHours"),
            # Cadence matters, not just presence: readings arriving less
            # often than every ten minutes do not count as reporting. When
            # cadence_ok is false while last_reading_hours_ago is small, the
            # station is sending -- just too sparsely.
            "cadence_ok": reciprocity.get("cadenceOk"),
            "last_reading_hours_ago": reciprocity.get("lastReadingAgoH"),
        }
