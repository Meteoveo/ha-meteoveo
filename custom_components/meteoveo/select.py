"""How far back the radar playback reaches (ADR-0866 D6).

A ``select`` in the configuration category: it changes what the camera next
to it shows, not a reading. The value is restored after a restart, so a
dashboard set to twelve hours does not snap back to one every time Home
Assistant comes up.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HomeCoordinator, MeteoVeoConfigEntry
from .entity import add_when_allowed
from .home import has_plus
from .radar import RADAR_WINDOWS, RadarWindow

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    add_when_allowed(
        hass,
        entry,
        async_add_entities,
        platform="select",
        unique_id=f"{runtime.base_id}_radar_window",
        allowed=has_plus,
        build=lambda: [RadarWindowSelect(runtime.home, runtime.radar_window)],
    )


class RadarWindowSelect(CoordinatorEntity[HomeCoordinator], SelectEntity, RestoreEntity):
    """1, 3, 6, 12 or 24 hours of radar playback."""

    _attr_has_entity_name = True
    entity_description = SelectEntityDescription(
        key="radar_window",
        translation_key="radar_window",
        entity_category=EntityCategory.CONFIG,
        options=list(RADAR_WINDOWS),
    )

    def __init__(self, coordinator: HomeCoordinator, window: RadarWindow) -> None:
        super().__init__(coordinator)
        runtime = coordinator.config_entry.runtime_data
        self._attr_unique_id = f"{runtime.base_id}_radar_window"
        self._attr_device_info = runtime.device_info
        self._window = window

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The chosen window is the user's setting, not something the service
        # knows, so Home Assistant's own state is where it comes back from.
        if (last := await self.async_get_last_state()) is not None:
            self._window.restore(last.state)
        self.async_on_remove(self._window.subscribe(self._handle_window_change))

    @property
    def available(self) -> bool:
        return (
            super().available
            and has_plus(self.coordinator.data)
            and not self._window.refused
        )

    @property
    def current_option(self) -> str:
        return self._window.option

    async def async_select_option(self, option: str) -> None:
        self._window.choose(option)
        self.async_write_ha_state()

    @callback
    def _handle_window_change(self) -> None:
        self.async_write_ha_state()
