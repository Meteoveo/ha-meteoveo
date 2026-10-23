"""Reading the home view (``GET /v1/integration/home``, contract v1).

Pure functions, so the mapping from the service's shape to what Home
Assistant shows can be tested without a running instance. Field names and
units are fixed by the contract: ``...C`` degrees Celsius, ``...Pct`` percent,
``...Hpa`` hPa, ``...Ms`` m/s, ``...Mm`` mm, ``...Deg`` degrees. A ``null`` is
"no data" and stays ``None`` -- never zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from homeassistant.util import dt as dt_util

WARNING_LEVELS = ("yellow", "orange", "red")


def _num(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    """Forecast items leave out what is unknown rather than carrying None."""
    if value is not None:
        target[key] = value


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return dt_util.parse_datetime(value)


def hourly_forecast(home: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The hourly forecast in Home Assistant's ``Forecast`` shape."""
    items: list[dict[str, Any]] = []
    for hour in (home or {}).get("hourly") or []:
        if not isinstance(hour, Mapping) or not hour.get("at"):
            continue
        item: dict[str, Any] = {"datetime": hour["at"]}
        _put(item, "condition", hour.get("condition"))
        _put(item, "native_temperature", _num(hour.get("tempC")))
        _put(item, "native_apparent_temperature", _num(hour.get("feelsLikeC")))
        _put(item, "humidity", _num(hour.get("humidityPct")))
        _put(item, "native_precipitation", _num(hour.get("precipMm")))
        _put(item, "precipitation_probability", _num(hour.get("precipProbPct")))
        _put(item, "native_wind_speed", _num(hour.get("windMs")))
        _put(item, "native_wind_gust_speed", _num(hour.get("gustMs")))
        _put(item, "wind_bearing", _num(hour.get("windBearingDeg")))
        _put(item, "uv_index", _num(hour.get("uvIndex")))
        if isinstance(hour.get("isDaylight"), bool):
            item["is_daytime"] = hour["isDaylight"]
        items.append(item)
    return items


def daily_forecast(home: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The daily forecast in Home Assistant's ``Forecast`` shape.

    Days marked ``trend`` (8-14: a model trend rather than a forecast) are
    left out. The MeteoVeo apps show them visibly apart; Home Assistant's
    forecast format has no way to mark a day as a trend, so including them
    would present them as ordinary forecast days.
    """
    items: list[dict[str, Any]] = []
    for day in (home or {}).get("daily") or []:
        if not isinstance(day, Mapping) or day.get("trend") is True:
            continue
        date = dt_util.parse_date(day.get("date") or "")
        if date is None:
            continue
        item: dict[str, Any] = {"datetime": dt_util.start_of_local_day(date).isoformat()}
        _put(item, "condition", day.get("condition"))
        _put(item, "native_temperature", _num(day.get("tempMaxC")))
        _put(item, "native_templow", _num(day.get("tempMinC")))
        _put(item, "native_precipitation", _num(day.get("precipMm")))
        _put(item, "precipitation_probability", _num(day.get("precipProbPct")))
        _put(item, "native_wind_speed", _num(day.get("windMs")))
        _put(item, "native_wind_gust_speed", _num(day.get("gustMs")))
        _put(item, "wind_bearing", _num(day.get("windBearingDeg")))
        _put(item, "uv_index", _num(day.get("uvIndex")))
        items.append(item)
    return items


def next_hour_attributes(next_hour: Mapping[str, Any]) -> dict[str, Any]:
    """Attributes of the rain-soon sensor, in snake case."""
    steps = []
    for step in next_hour.get("steps") or []:
        if not isinstance(step, Mapping):
            continue
        steps.append(
            {
                "at": step.get("at"),
                "lead_minutes": step.get("leadMinutes"),
                "band": step.get("band"),
                "source": step.get("source"),
                "uncertain": step.get("uncertain"),
            }
        )
    return {
        "rain_now": next_hour.get("rainNow"),
        "starts_at": next_hour.get("rainStartsAt"),
        "ends_at": next_hour.get("rainEndsAt"),
        "issued_at": next_hour.get("issuedAt"),
        "age_minutes": next_hour.get("ageMinutes"),
        "steps": steps,
    }


def warnings_list(home: Mapping[str, Any] | None) -> list[dict[str, Any]] | None:
    """Active warnings, or None when the service said nothing about them."""
    raw = (home or {}).get("warnings")
    if not isinstance(raw, list):
        return None
    return [
        {
            "level": item.get("level"),
            "phenomenon": item.get("phenomenon"),
            "phenomenon_name": item.get("phenomenonName"),
            "headline": item.get("headline"),
            "onset": item.get("onset"),
            "expires": item.get("expires"),
        }
        for item in raw
        if isinstance(item, Mapping)
    ]


def highest_level(warnings: list[dict[str, Any]]) -> str:
    """``none``, ``yellow``, ``orange`` or ``red``."""
    found = [WARNING_LEVELS.index(w["level"]) for w in warnings if w.get("level") in WARNING_LEVELS]
    return WARNING_LEVELS[max(found)] if found else "none"
