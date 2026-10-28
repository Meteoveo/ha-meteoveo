"""Turning Home Assistant states into an upload."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Protocol

from .client import InvalidCredentials, MeteoVeoClient, ServiceUnavailable
from .wu_payload import PRESSURE_ABSOLUTE, build_wu_params

_LOGGER = logging.getLogger(__name__)


class StateLookup(Protocol):
    """The part of Home Assistant's state machine this module needs."""

    def get(self, entity_id: str) -> Any: ...


def collect_readings(
    states: StateLookup, selection: Mapping[str, str]
) -> dict[str, tuple[Any, str]]:
    """Read the mapped entities.

    Values are passed through as they are. Deciding what counts as usable
    belongs in one place -- the payload builder -- so that the rules cannot
    drift apart between here and there.
    """
    readings: dict[str, tuple[Any, str]] = {}
    for measurement, entity_id in selection.items():
        state = states.get(entity_id)
        if state is None:
            # Renamed or removed since setup. Skipping is right: an upload
            # missing one field is better than one carrying a stale value.
            continue
        readings[measurement] = (state.state, state.attributes.get("unit_of_measurement", ""))
    return readings


async def upload_once(
    client: MeteoVeoClient,
    states: StateLookup,
    selection: Mapping[str, str],
    *,
    now_iso: str,
    pressure_kind: str = PRESSURE_ABSOLUTE,
) -> bool:
    """Read, convert and send. Returns True when something was sent."""
    readings = collect_readings(states, selection)
    fields = build_wu_params(readings, pressure_kind=pressure_kind)
    if not fields:
        return False

    try:
        return await client.async_upload(fields, now_iso=now_iso)
    except InvalidCredentials:
        # Let this surface: the upload timer turns it into a re-authentication
        # prompt, and silently retrying with a replaced key never recovers.
        raise
    except ServiceUnavailable as failure:
        # Logged once per occurrence at debug level; the next attempt is a
        # minute away and the coordinator already reports service health.
        _LOGGER.debug("upload skipped: %s", failure)
        return False
