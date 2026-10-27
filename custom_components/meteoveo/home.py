"""Reading the home view (``GET /v1/integration/home``, contract v1).

Pure functions, so the mapping from the service's shape to what Home
Assistant shows can be tested without a running instance. Field names and
units are fixed by the contract: ``...C`` degrees Celsius, ``...Pct`` percent,
``...Hpa`` hPa, ``...Ms`` m/s, ``...Mm`` mm, ``...Deg`` degrees. A ``null`` is
"no data" and stays ``None`` -- never zero.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
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
        "age_minutes": _age_minutes(next_hour),
        "steps": steps,
    }


def _age_minutes(next_hour: Mapping[str, Any]) -> int | None:
    """Minutes since the nowcast run, counted now rather than taken from the reply.

    A 304 keeps the previous reply, whose ``ageMinutes`` was true when it was
    sent; counting from ``issuedAt`` keeps the age honest while the reply is
    reused. The server's figure is only the fallback.
    """
    issued = dt_util.parse_datetime(str(next_hour.get("issuedAt") or ""))
    if issued is None:
        age = next_hour.get("ageMinutes")
        return age if isinstance(age, int) else None
    return max(0, int((dt_util.utcnow() - issued).total_seconds() // 60))


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


# --- Derived values (ADR-0827 B1/B2) -------------------------------------------
#
# Computed from what the home view already carries; no extra request. A dew
# point is arithmetic on the measured temperature and humidity, not new data.

RAIN_BANDS = ("none", "light", "moderate", "heavy")


def current_hour(view: Mapping[str, Any] | None, now: datetime) -> Mapping[str, Any] | None:
    """The hourly item whose hour contains ``now``, or None."""
    for hour in (view or {}).get("hourly") or []:
        start = parse_time(hour.get("at")) if isinstance(hour, Mapping) else None
        if start is not None and start <= now < start + timedelta(hours=1):
            return hour
    return None


def dew_point(temp_c: Any, humidity_pct: Any) -> float | None:
    """Magnus formula (Sonntag 1990 constants), to 0.1 °C."""
    temp, rh = _num(temp_c), _num(humidity_pct)
    if temp is None or rh is None or not 0 < rh <= 100:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(rh / 100) + a * temp / (b + temp)
    return round(b * gamma / (a - gamma), 1)


def minutes_to_rain(next_hour: Mapping[str, Any] | None, now: datetime) -> int | None:
    """0 while it rains, minutes until the next rain, None when none is expected."""
    if not next_hour:
        return None
    if next_hour.get("rainNow") is True:
        return 0
    start = parse_time(next_hour.get("rainStartsAt"))
    if start is None:
        return None
    return max(0, math.ceil((start - now).total_seconds() / 60))


def rain_intensity_now(next_hour: Mapping[str, Any] | None, now: datetime) -> str | None:
    """The band of the latest step that has begun (``none`` … ``heavy``)."""
    band = None
    for step in (next_hour or {}).get("steps") or []:
        at = parse_time(step.get("at")) if isinstance(step, Mapping) else None
        if at is not None and at <= now and step.get("band") in RAIN_BANDS:
            band = step["band"]
    if band is None:
        steps = (next_hour or {}).get("steps") or []
        first = steps[0] if steps and isinstance(steps[0], Mapping) else {}
        band = first.get("band") if first.get("band") in RAIN_BANDS else None
    return band


def uv_max_today(view: Mapping[str, Any] | None, now: datetime) -> float | int | None:
    """Today's UV maximum from the daily forecast (the local calendar day)."""
    today = dt_util.as_local(now).date().isoformat()
    for day in (view or {}).get("daily") or []:
        if isinstance(day, Mapping) and day.get("date") == today:
            return _num(day.get("uvIndex"))
    return None


def active_levels(warnings: list[dict[str, Any]] | None, now: datetime) -> set[str]:
    """The levels with a warning in force now (started, not yet expired)."""
    levels: set[str] = set()
    for warning in warnings or []:
        onset, expires = parse_time(warning.get("onset")), parse_time(warning.get("expires"))
        if onset is not None and onset <= now and (expires is None or now < expires):
            if warning.get("level") in WARNING_LEVELS:
                levels.add(warning["level"])
    return levels


def next_warning_onset(warnings: list[dict[str, Any]] | None, now: datetime) -> datetime | None:
    """When the next warning that has not started yet begins."""
    upcoming = [
        onset
        for warning in warnings or []
        if (onset := parse_time(warning.get("onset"))) is not None and onset > now
    ]
    return min(upcoming) if upcoming else None


def warning_id(warning: Mapping[str, Any]) -> str:
    """Identity of a warning across refreshes: phenomenon, level and onset."""
    return f"{warning.get('phenomenon')}|{warning.get('level')}|{warning.get('onset')}"


# --- The account level and the lightning block (ADR-0866) ------------------
#
# Both have been in the contract's answer from the start; until 0.3.0 nothing
# read them. ``level`` is ``free`` or ``plus`` -- the service deliberately
# does not say whether the level was bought or earned by a reporting station,
# so neither does Home Assistant. ``lightning`` is ``{"locked": true}`` for a
# free account (the capability exists, the data does not), ``null`` when the
# source itself is silent, and the full block on Plus.

ACCOUNT_LEVELS = ("free", "plus")

#: "Nearby" is the product's own inner radius; a strike at 44 km is data, not
#: an alert.
LIGHTNING_NEARBY_KM = 30


def account_level(view: Mapping[str, Any] | None) -> str | None:
    """``free``, ``plus``, or None when the answer did not say.

    An answer without the field must never read as ``free``: that would show
    a paying account as free during a partial outage.
    """
    level = (view or {}).get("level")
    return level if level in ACCOUNT_LEVELS else None


def has_plus(view: Mapping[str, Any] | None) -> bool:
    """Whether the account behind this entry has the Plus level right now."""
    return account_level(view) == "plus"


def lightning_block(view: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The lightning block, or None when the source said nothing."""
    block = (view or {}).get("lightning")
    return block if isinstance(block, Mapping) else None


def lightning_unlocked(view: Mapping[str, Any] | None) -> bool:
    """Whether the account may see lightning data right now."""
    block = lightning_block(view)
    return block is not None and block.get("locked") is False


def lightning_nearby(view: Mapping[str, Any] | None) -> bool | None:
    """Whether a strike was counted inside the nearby radius."""
    block = lightning_block(view)
    if block is None:
        return None
    count = _num(block.get(f"count{LIGHTNING_NEARBY_KM}km"))
    return None if count is None else count > 0


def nearest_lightning_km(view: Mapping[str, Any] | None) -> float | int | None:
    """Distance to the closest counted strike, in km."""
    return _num((lightning_block(view) or {}).get("nearestKm"))


def lightning_attributes(view: Mapping[str, Any] | None) -> dict[str, Any]:
    """Attributes of the lightning entities, in snake case."""
    block = lightning_block(view) or {}
    return {
        "nearest_km": _num(block.get("nearestKm")),
        "bearing_deg": _num(block.get("bearingDeg")),
        "count_15km": _num(block.get("count15km")),
        "count_30km": _num(block.get("count30km")),
        "count_50km": _num(block.get("count50km")),
        "last_strike_at": block.get("lastStrikeAt"),
        "window_minutes": _num(block.get("windowMinutes")),
    }
