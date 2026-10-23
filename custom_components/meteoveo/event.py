"""An event for every new official weather warning (ADR-0827 B2)."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MeteoVeoConfigEntry
from .entity import MeteoVeoEntity
from .home import WARNING_LEVELS, warning_id, warnings_list

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([WarningEvent(entry.runtime_data.home)])


class WarningEvent(MeteoVeoEntity, EventEntity):
    """Fires when a warning appears that was not there before.

    The event type is the level; the warning's fields are the event's
    attributes. Warnings already present when Home Assistant starts do not
    fire -- a restart must not notify again about what is already known.
    """

    entity_description = EventEntityDescription(
        key="warning",
        translation_key="warning",
        event_types=list(WARNING_LEVELS),
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "warning")
        self._seen: set[str] = {warning_id(w) for w in warnings_list(self._view) or []}

    @callback
    def _handle_coordinator_update(self) -> None:
        for warning in warnings_list(self._view) or []:
            key = warning_id(warning)
            if key in self._seen:
                continue
            self._seen.add(key)
            if warning.get("level") in WARNING_LEVELS:
                self._trigger_event(
                    warning["level"],
                    {k: warning.get(k) for k in ("phenomenon", "phenomenon_name", "headline", "onset", "expires")},
                )
        super()._handle_coordinator_update()
