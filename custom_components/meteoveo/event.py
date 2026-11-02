"""Events for every new official weather warning.

Two entities over the same stream of warnings (ADR-0827 B2, ADR-0935 D4), so
Home Assistant's own trigger picker offers both axes of the official warning
without anyone writing a template:

* **New warning** -- the event type is the *level* (yellow, orange, red);
* **New warning by phenomenon** -- the event type is the AEMET Meteoalerta
  *phenomenon* (rain, thunderstorms, wind, ...).

Neither reinterprets the warning: the level, the phenomenon, the probability
band and the headline are AEMET's, passed through.
"""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MeteoVeoConfigEntry
from .entity import MeteoVeoEntity
from .home import (
    UNKNOWN_PHENOMENON,
    WARNING_LEVELS,
    WARNING_PHENOMENA,
    phenomenon_event_type,
    warning_event_body,
    warning_id,
    warnings_list,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.home
    async_add_entities([WarningEvent(coordinator), WarningPhenomenonEvent(coordinator)])


class _NewWarningEvent(MeteoVeoEntity, EventEntity):
    """Fires when a warning appears that was not there before.

    Warnings already present when Home Assistant starts do not fire -- a
    restart must not notify again about what is already known. A reply with no
    warnings block at all fires nothing either: silence is not an event
    (ADR-0935 D7).

    Subclasses say what the event type of a warning is.
    """

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._seen: set[str] = {warning_id(w) for w in warnings_list(self._view) or []}

    def _event_type(self, warning: Mapping[str, Any]) -> str | None:
        """The type this warning fires under, or None not to fire it."""
        raise NotImplementedError

    @callback
    def _handle_coordinator_update(self) -> None:
        for warning in warnings_list(self._view) or []:
            key = warning_id(warning)
            if key in self._seen:
                continue
            self._seen.add(key)
            event_type = self._event_type(warning)
            if event_type is not None:
                self._trigger_event(event_type, warning_event_body(warning))
        super()._handle_coordinator_update()


class WarningEvent(_NewWarningEvent):
    """A new warning, fired under its level."""

    entity_description = EventEntityDescription(
        key="warning",
        translation_key="warning",
        event_types=list(WARNING_LEVELS),
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "warning")

    def _event_type(self, warning: Mapping[str, Any]) -> str | None:
        level = warning.get("level")
        return level if level in WARNING_LEVELS else None


class WarningPhenomenonEvent(_NewWarningEvent):
    """A new warning, fired under its AEMET phenomenon.

    Every Meteoalerta code is declared, so the trigger picker lists them all
    in the user's own language -- including the ones this place has never had.
    A code we do not know fires under ``other`` with the raw code in the body;
    that is a container for the unexpected, not a guess at its meaning.
    """

    entity_description = EventEntityDescription(
        key="warning_phenomenon",
        translation_key="warning_phenomenon",
        event_types=[code.lower() for code in WARNING_PHENOMENA] + [UNKNOWN_PHENOMENON],
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "warning_phenomenon")

    def _event_type(self, warning: Mapping[str, Any]) -> str | None:
        return phenomenon_event_type(warning.get("phenomenon"))
