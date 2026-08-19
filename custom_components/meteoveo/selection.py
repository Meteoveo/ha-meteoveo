"""Mapping measurements to Home Assistant entities.

Not every station reports every measurement. Someone with no solar sensor
must be able to say "not available" and move on -- an integration that
demands a value for everything is an integration that cannot be set up.

An unmapped measurement is dropped from the stored configuration rather than
kept as a placeholder, so the rest of the code only ever sees real entity
ids.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .wu_payload import MEASUREMENTS_BY_KEY

#: Sentinel offered in the config flow for "this station has no such sensor".
#: A plain empty value would be indistinguishable from an unanswered question.
NOT_AVAILABLE = "n/a"


def _is_unmapped(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() == NOT_AVAILABLE
    return False


def validate_selection(selection: Mapping[str, Any]) -> dict[str, str]:
    """Return the mapping with unmapped measurements removed.

    Raises ``ValueError`` for an unknown measurement key, or when more than
    one entity is offered for a single measurement: the upload protocol
    carries one field per measurement, and merging two sources into one
    series would make the result meaningless.
    """
    cleaned: dict[str, str] = {}
    for key, value in selection.items():
        if key not in MEASUREMENTS_BY_KEY:
            raise ValueError(f"unknown measurement: {key}")
        if _is_unmapped(value):
            continue
        if not isinstance(value, str):
            raise ValueError(f"{key}: exactly one entity is allowed per measurement")
        cleaned[key] = value
    return cleaned


def selected_entity_ids(selection: Mapping[str, Any]) -> list[str]:
    """Entity ids to watch, sorted and without duplicates.

    One entity may legitimately feed two measurements -- some integrations
    expose wind speed and gust from a single entity -- so duplicates are
    collapsed rather than treated as an error.
    """
    cleaned = validate_selection(selection)
    return sorted(set(cleaned.values()))


def measurement_keys_for(entity_id: str, selection: Mapping[str, Any]) -> Iterable[str]:
    """Which measurements a given entity feeds."""
    return (key for key, value in validate_selection(selection).items() if value == entity_id)
