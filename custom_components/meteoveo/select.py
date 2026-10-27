"""What the radar playback shows: how far back, and how wide (ADR-0866 D6).

Two ``select`` entities in the configuration category: they change what the
camera next to them shows, not a reading. Both values are restored after a
restart, so a dashboard set to twelve hours over the peninsula does not snap
back to the last hour around the town every time Home Assistant comes up.
"""

from __future__ import annotations

from functools import partial

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HomeCoordinator, MeteoVeoConfigEntry, MeteoVeoData
from .entity import add_when_allowed
from .home import has_plus
from .radar import RADAR_EXTENTS, RADAR_WINDOWS, RadarView

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    for entity_class in (RadarWindowSelect, RadarExtentSelect):
        add_when_allowed(
            hass,
            entry,
            async_add_entities,
            platform="select",
            unique_id=f"{runtime.base_id}_{entity_class.key}",
            allowed=has_plus,
            build=partial(_build, entity_class, runtime),
        )


def _build(entity_class: type[_RadarViewSelect], runtime: MeteoVeoData) -> list[SelectEntity]:
    return [entity_class(runtime.home, runtime.radar_view)]


class _RadarViewSelect(CoordinatorEntity[HomeCoordinator], SelectEntity, RestoreEntity):
    """One of the playback's two choices, stored in the entry's shared view."""

    _attr_has_entity_name = True
    #: Suffix of the unique id, and the translation key.
    key: str

    def __init__(self, coordinator: HomeCoordinator, view: RadarView) -> None:
        super().__init__(coordinator)
        runtime = coordinator.config_entry.runtime_data
        self._attr_unique_id = f"{runtime.base_id}_{self.key}"
        self._attr_device_info = runtime.device_info
        self._view = view

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The choice is the user's setting, not something the service knows,
        # so Home Assistant's own state is where it comes back from.
        if (last := await self.async_get_last_state()) is not None:
            self._restore(last.state)
        self.async_on_remove(self._view.subscribe(self._handle_view_change))

    @property
    def available(self) -> bool:
        return (
            super().available
            and has_plus(self.coordinator.data)
            and not self._view.refused
        )

    @callback
    def _handle_view_change(self) -> None:
        self.async_write_ha_state()

    def _restore(self, value: str) -> None:
        raise NotImplementedError


class RadarWindowSelect(_RadarViewSelect):
    """1, 3, 6, 12 or 24 hours of radar playback."""

    key = "radar_window"
    entity_description = SelectEntityDescription(
        key="radar_window",
        translation_key="radar_window",
        entity_category=EntityCategory.CONFIG,
        options=list(RADAR_WINDOWS),
    )

    @property
    def current_option(self) -> str:
        return self._view.window

    async def async_select_option(self, option: str) -> None:
        self._view.choose_window(option)
        self.async_write_ha_state()

    def _restore(self, value: str) -> None:
        self._view.restore_window(value)


class RadarExtentSelect(_RadarViewSelect):
    """How wide the picture is: around the town, the region, or the peninsula.

    There is no Canaries option: our radar field measures nothing there, so
    it would only ever render an empty map.
    """

    key = "radar_extent"
    entity_description = SelectEntityDescription(
        key="radar_extent",
        translation_key="radar_extent",
        entity_category=EntityCategory.CONFIG,
        options=list(RADAR_EXTENTS),
    )

    @property
    def current_option(self) -> str:
        return self._view.extent

    async def async_select_option(self, option: str) -> None:
        self._view.choose_extent(option)
        self.async_write_ha_state()

    def _restore(self, value: str) -> None:
        self._view.restore_extent(value)
