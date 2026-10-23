"""The weather entity: conditions now, hourly and daily forecast."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HomeCoordinator, MeteoVeoConfigEntry
from .home import daily_forecast, hourly_forecast

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MeteoVeoWeather(entry.runtime_data.home)])


class MeteoVeoWeather(SingleCoordinatorWeatherEntity[HomeCoordinator]):
    """Conditions and forecast for the entry's place.

    Named after the device (the town), so it reads ``weather.<town>``.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "forecast"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(self, coordinator: HomeCoordinator) -> None:
        super().__init__(coordinator)
        runtime = coordinator.config_entry.runtime_data
        self._attr_unique_id = f"{runtime.base_id}_forecast"
        self._attr_device_info = runtime.device_info

    @property
    def _current(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("current") or {}

    @property
    def condition(self) -> str | None:
        return self._current.get("condition")

    @property
    def native_temperature(self) -> float | None:
        return self._current.get("tempC")

    @property
    def humidity(self) -> float | None:
        return self._current.get("humidityPct")

    @property
    def native_pressure(self) -> float | None:
        return self._current.get("pressureHpa")

    @property
    def native_wind_speed(self) -> float | None:
        return self._current.get("windMs")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._current.get("gustMs")

    @property
    def wind_bearing(self) -> float | None:
        return self._current.get("windBearingDeg")

    @property
    def attribution(self) -> str | None:
        return (self.coordinator.data or {}).get("attribution")

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        return hourly_forecast(self.coordinator.data)  # type: ignore[return-value]

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        return daily_forecast(self.coordinator.data)  # type: ignore[return-value]
