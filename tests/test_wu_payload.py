"""Measurement catalogue and unit conversion.

A wrong conversion factor does not raise an error -- it produces a plausible
but false reading. Every conversion below is therefore pinned to a known
reference point that can be checked by hand.
"""

from __future__ import annotations

import math

import pytest

from custom_components.meteoveo.wu_payload import (
    MEASUREMENTS,
    PRESSURE_SEA_LEVEL,
    build_wu_params,
)


def test_catalogue_is_complete():
    assert {m.key for m in MEASUREMENTS} == {
        "temperature",
        "humidity",
        "pressure",
        "wind_speed",
        "wind_gust",
        "wind_direction",
        "daily_rain",
        "solar_radiation",
    }
    for measurement in MEASUREMENTS:
        assert measurement.api_field, f"{measurement.key}: no API field"
        assert measurement.ha_unit, f"{measurement.key}: no Home Assistant unit"


class TestUnitConversion:
    def test_celsius_to_fahrenheit(self):
        # 0 C = 32 F; 37.7778 C = 100 F; -40 is where the scales meet.
        assert build_wu_params({"temperature": (0.0, "°C")})["tempf"] == pytest.approx(32.0)
        assert build_wu_params({"temperature": (37.7778, "°C")})["tempf"] == pytest.approx(
            100.0, abs=0.01
        )
        assert build_wu_params({"temperature": (-40.0, "°C")})["tempf"] == pytest.approx(-40.0)

    def test_value_outside_air_temperature_range_is_dropped(self):
        # 100 C is 212 F -- not an air temperature anywhere on Earth. It is
        # rejected here rather than by the server.
        assert build_wu_params({"temperature": (100.0, "°C")}) == {}

    def test_fahrenheit_input_is_not_converted_twice(self):
        assert build_wu_params({"temperature": (70.0, "°F")})["tempf"] == pytest.approx(70.0)

    def test_hectopascal_to_inches_of_mercury(self):
        # Standard atmosphere: 1013.25 hPa = 29.9213 inHg.
        assert build_wu_params({"pressure": (1013.25, "hPa")})["absbaromin"] == pytest.approx(
            29.9213, abs=1e-4
        )

    # Tolerances follow sensor resolution, not the conversion constant: an
    # anemometer resolves about 0.1 m/s (0.22 mph), so two decimals are already
    # 45 times finer. Demanding more would only be testing arithmetic.
    def test_metres_per_second_to_mph(self):
        assert build_wu_params({"wind_speed": (1.0, "m/s")})["windspeedmph"] == pytest.approx(
            2.236936, abs=0.01
        )

    def test_kilometres_per_hour_to_mph(self):
        assert build_wu_params({"wind_gust": (100.0, "km/h")})["windgustmph"] == pytest.approx(
            62.1371, abs=0.01
        )

    def test_millimetres_to_inches(self):
        assert build_wu_params({"daily_rain": (25.4, "mm")})["dailyrainin"] == pytest.approx(1.0)

    def test_units_that_need_no_conversion(self):
        params = build_wu_params(
            {
                "humidity": (58.0, "%"),
                "wind_direction": (270.0, "°"),
                "solar_radiation": (812.0, "W/m²"),
            }
        )
        assert params["humidity"] == pytest.approx(58.0)
        assert params["winddir"] == pytest.approx(270.0)
        assert params["solarradiation"] == pytest.approx(812.0)


class TestUnusableStates:
    """Home Assistant states are strings and are often unavailable."""

    @pytest.mark.parametrize(
        "state", [None, "unknown", "unavailable", "", "not-a-number", float("nan")]
    )
    def test_unusable_state_is_omitted_rather_than_sent_as_zero(self, state):
        # Zero is a valid reading. A gap must never look like a measurement.
        params = build_wu_params({"temperature": (state, "°C"), "humidity": (58.0, "%")})
        assert "tempf" not in params
        assert params["humidity"] == pytest.approx(58.0)

    def test_all_states_unusable_yields_nothing_to_upload(self):
        assert build_wu_params({"temperature": (None, "°C")}) == {}

    def test_unknown_unit_is_omitted(self):
        # A missing field is recoverable; a wrongly scaled one is not.
        assert build_wu_params({"temperature": (20.0, "K")}) == {}

    def test_unknown_measurement_key_is_omitted(self):
        assert build_wu_params({"no_such_measurement": (1.0, "°C")}) == {}


class TestPlausibility:
    """The same bounds the server applies, checked before the request."""

    def test_impossible_humidity_is_dropped(self):
        assert "humidity" not in build_wu_params({"humidity": (150.0, "%")})

    def test_impossible_wind_direction_is_dropped(self):
        assert "winddir" not in build_wu_params({"wind_direction": (400.0, "°")})

    def test_negative_rainfall_is_dropped(self):
        assert "dailyrainin" not in build_wu_params({"daily_rain": (-3.0, "mm")})


def test_rounding_is_per_measurement():
    # Temperature: two decimals is 0.006 C -- ample.
    params = build_wu_params({"temperature": (21.37, "°C")})
    assert params["tempf"] == pytest.approx(70.47, abs=0.005)
    assert len(str(params["tempf"]).split(".")[-1]) <= 2

    # Pressure: two decimals would collapse readings 0.25 hPa apart into one
    # value. Neighbouring readings must stay distinguishable.
    low = build_wu_params({"pressure": (1013.25, "hPa")})["absbaromin"]
    high = build_wu_params({"pressure": (1013.50, "hPa")})["absbaromin"]
    assert low != high, "pressure resolution lost to rounding"

    # Rainfall: tipping buckets step in 0.1 mm.
    before = build_wu_params({"daily_rain": (12.3, "mm")})["dailyrainin"]
    after = build_wu_params({"daily_rain": (12.4, "mm")})["dailyrainin"]
    assert before != after, "rainfall resolution lost to rounding"


def test_not_a_number_never_reaches_the_request():
    assert build_wu_params({"pressure": (math.nan, "hPa")}) == {}


class TestPressureKind:
    """Absolute, or already reduced to sea level (MeteoVeo ADR-0844).

    The service stores STATION-LEVEL pressure, and every consumer reduces it
    with the station's elevation. A console that reports the already reduced
    ("relative") value must therefore not travel in the absolute field: it
    would be reduced a second time, about 0.12 hPa per metre -- 6 hPa at 50 m,
    which is a whole weather situation. The upload protocol carries a separate
    field for the reduced value, and the server raises it back using the
    station's elevation, so the round trip returns what the barometer said.
    """

    def test_absolute_is_the_default(self):
        params = build_wu_params({"pressure": (1013.25, "hPa")})
        assert "absbaromin" in params
        assert "baromin" not in params

    def test_a_reduced_reading_travels_in_its_own_field(self):
        params = build_wu_params(
            {"pressure": (1013.25, "hPa")}, pressure_kind=PRESSURE_SEA_LEVEL
        )
        assert "absbaromin" not in params
        assert params["baromin"] == pytest.approx(29.9213, abs=1e-4)

    def test_only_the_field_name_changes(self):
        readings = {"pressure": (997.4, "hPa"), "temperature": (12.0, "°C")}
        absolute = build_wu_params(readings)
        reduced = build_wu_params(readings, pressure_kind=PRESSURE_SEA_LEVEL)
        assert reduced["baromin"] == absolute["absbaromin"]
        assert reduced["tempf"] == absolute["tempf"]

    def test_an_unrecognised_kind_is_treated_as_absolute(self):
        # A hand-edited option, or one written by a newer version: the safe
        # reading is the one the integration has always sent.
        params = build_wu_params({"pressure": (1013.25, "hPa")}, pressure_kind="qff")
        assert "absbaromin" in params
        assert "baromin" not in params

    def test_pressure_is_the_only_measurement_with_a_second_field(self):
        assert {m.key for m in MEASUREMENTS if m.sea_level_api_field} == {"pressure"}
