"""Measurement catalogue and upload payload builder.

Unit conversion is where this integration can fail most quietly. A wrong
factor does not raise an error -- it produces a plausible but false reading,
and from then on the station looks broken to its owner for a fault that lives
here. Every conversion therefore has a known, hand-checkable reference point
in the test suite.

The catalogue below is the contract: the config flow offers entities based on
it, and uploads are built from it. One entity per measurement per station --
the upload protocol carries a single field per measurement, and mixing two
sources into one series would make the data meaningless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

# --- Conversion constants ---------------------------------------------------

_MM_PER_INCH = 25.4
_HPA_PER_INHG = 33.863886666667
_MPH_PER_MS = 2.236936
_MPH_PER_KMH = 0.621371

# --- How the barometer reports (MeteoVeo ADR-0844) -------------------------
#
# The service stores STATION-LEVEL pressure and every consumer reduces it to
# sea level with the station's elevation. A console that already did the
# reduction ("relative" pressure) must therefore not send its value as
# absolute: it would be reduced a second time, about 0.12 hPa per metre --
# 6 hPa at 50 m, which is a different weather situation. The upload protocol
# carries a separate field for the reduced value, and the server raises it
# back with the station's elevation, so nothing is lost either way.

#: The pressure measured at the station (QFE).
PRESSURE_ABSOLUTE = "absolute"
#: The same reading already reduced to sea level (QFF; "relative" on most
#: consoles), which is what they tend to show by default.
PRESSURE_SEA_LEVEL = "sea_level"
PRESSURE_KINDS: tuple[str, ...] = (PRESSURE_ABSOLUTE, PRESSURE_SEA_LEVEL)


def _celsius_to_fahrenheit(value: float) -> float:
    return value * 9.0 / 5.0 + 32.0


@dataclass(frozen=True)
class Measurement:
    """One measurement: what the API expects and how to get there."""

    key: str
    #: Field name in the upload request.
    api_field: str
    #: Preferred Home Assistant unit, used to rank candidate entities.
    ha_unit: str
    #: Accepted units mapped to their converter. The identity case is listed
    #: explicitly so an entity that already reports imperial units is not
    #: converted twice.
    converters: Mapping[str, Callable[[float], float]]
    #: Plausibility bounds, applied *after* conversion. The server enforces
    #: the same limits; checking here means an out-of-range sensor is reported
    #: as such locally instead of surfacing as an opaque server rejection.
    minimum: float | None = None
    maximum: float | None = None
    #: Field to use when the value arrives already reduced to sea level.
    #: Only pressure has one -- for every other measurement the question
    #: does not arise.
    sea_level_api_field: str | None = None
    #: Home Assistant device class, used to filter the entity picker.
    device_class: str | None = None
    #: Decimal places to send. Deliberately not uniform: two decimals would
    #: discard roughly 0.3 hPa of pressure and 0.25 mm of rainfall -- which is
    #: the signal itself, not noise.
    decimals: int = 2


MEASUREMENTS: tuple[Measurement, ...] = (
    Measurement(
        key="temperature",
        api_field="tempf",
        ha_unit="°C",
        converters={
            "°C": _celsius_to_fahrenheit,
            "C": _celsius_to_fahrenheit,
            "°F": lambda v: v,
            "F": lambda v: v,
        },
        # Bounds are in Fahrenheit, matching the transmitted unit: roughly
        # -62 °C to +65 °C, which brackets air temperature anywhere on Earth.
        minimum=-80.0,
        maximum=150.0,
        device_class="temperature",
    ),
    Measurement(
        key="humidity",
        api_field="humidity",
        ha_unit="%",
        converters={"%": lambda v: v},
        minimum=0.0,
        maximum=100.0,
        device_class="humidity",
    ),
    Measurement(
        # Pressure as measured at the station, by default. The server performs
        # the sea-level reduction using terrain elevation, which is why an
        # accurate station position matters. A console that only reports the
        # already reduced value says so in the config flow, and then the
        # reading travels in `baromin` instead.
        key="pressure",
        api_field="absbaromin",
        sea_level_api_field="baromin",
        ha_unit="hPa",
        converters={
            "hPa": lambda v: v / _HPA_PER_INHG,
            "mbar": lambda v: v / _HPA_PER_INHG,
            "inHg": lambda v: v,
        },
        minimum=0.0,
        maximum=40.0,
        device_class="atmospheric_pressure",
        # Four decimals in inHg is about 0.003 hPa -- finer than any consumer
        # barometer, so nothing measurable is lost.
        decimals=4,
    ),
    Measurement(
        key="wind_speed",
        api_field="windspeedmph",
        ha_unit="m/s",
        converters={
            "m/s": lambda v: v * _MPH_PER_MS,
            "km/h": lambda v: v * _MPH_PER_KMH,
            "mph": lambda v: v,
        },
        minimum=0.0,
        maximum=250.0,
        device_class="wind_speed",
    ),
    Measurement(
        key="wind_gust",
        api_field="windgustmph",
        ha_unit="m/s",
        converters={
            "m/s": lambda v: v * _MPH_PER_MS,
            "km/h": lambda v: v * _MPH_PER_KMH,
            "mph": lambda v: v,
        },
        minimum=0.0,
        maximum=250.0,
        device_class="wind_speed",
    ),
    Measurement(
        key="wind_direction",
        api_field="winddir",
        ha_unit="°",
        converters={"°": lambda v: v, "deg": lambda v: v},
        minimum=0.0,
        maximum=360.0,
    ),
    Measurement(
        # Rainfall accumulated since local midnight, not an interval total.
        # Many station integrations expose this directly; where they do not, a
        # Home Assistant utility meter on a daily cycle produces it.
        key="daily_rain",
        api_field="dailyrainin",
        ha_unit="mm",
        converters={"mm": lambda v: v / _MM_PER_INCH, "in": lambda v: v},
        minimum=0.0,
        maximum=40.0,
        device_class="precipitation",
        # Four decimals in inches is about 0.0025 mm; tipping buckets step in
        # 0.1 mm increments.
        decimals=4,
    ),
    Measurement(
        key="solar_radiation",
        api_field="solarradiation",
        ha_unit="W/m²",
        converters={"W/m²": lambda v: v, "W/m2": lambda v: v},
        minimum=0.0,
        maximum=2000.0,
        device_class="irradiance",
    ),
)

MEASUREMENTS_BY_KEY: Mapping[str, Measurement] = {m.key: m for m in MEASUREMENTS}


def _usable_number(value: Any) -> float | None:
    """Return a finite float, or None if the state cannot be trusted.

    Home Assistant states are strings and regularly carry ``unknown`` or
    ``unavailable``. Such a state is dropped rather than coerced to zero: zero
    is a valid reading, and a gap must never be indistinguishable from a
    measurement.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        if value.strip().lower() in {"", "unknown", "unavailable", "none"}:
            return None
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def build_wu_params(
    readings: Mapping[str, tuple[Any, str]],
    *,
    pressure_kind: str = PRESSURE_ABSOLUTE,
) -> dict[str, float]:
    """Build upload fields from selected entity states.

    ``readings`` maps a measurement key to ``(raw state, unit)``. Only usable
    values appear in the result; an empty result means there is nothing worth
    uploading, and the caller should skip the request entirely.

    ``pressure_kind`` says which field the pressure belongs in. Anything
    other than :data:`PRESSURE_SEA_LEVEL` means absolute -- an unreadable
    stored option must not silently change what a value means.
    """
    params: dict[str, float] = {}
    for key, (raw, unit) in readings.items():
        measurement = MEASUREMENTS_BY_KEY.get(key)
        if measurement is None:
            continue
        converter = measurement.converters.get(unit)
        if converter is None:
            # An unrecognised unit is skipped rather than guessed: a missing
            # field is recoverable, a wrongly scaled one is not.
            continue
        number = _usable_number(raw)
        if number is None:
            continue

        converted = converter(number)
        if math.isnan(converted) or math.isinf(converted):
            continue
        if measurement.minimum is not None and converted < measurement.minimum:
            continue
        if measurement.maximum is not None and converted > measurement.maximum:
            continue

        field = measurement.api_field
        if pressure_kind == PRESSURE_SEA_LEVEL and measurement.sea_level_api_field:
            field = measurement.sea_level_api_field
        params[field] = round(converted, measurement.decimals)
    return params
