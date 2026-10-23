"""The radar loop as an image entity (ADR-0833 R4).

An animated WEBP of the last hour of radar and the next hour's nowcast around
the place; any Home Assistant card plays it, no stream integration needed.
The picture is fetched only when Home Assistant asks for it -- that is, when
someone looks at it -- and at most once per ten-minute radar slot.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .client import ApiError, MeteoVeoError
from .coordinator import HomeCoordinator, MeteoVeoConfigEntry

PARALLEL_UPDATES = 0

#: The server renders a new loop when a new radar frame is usable.
SLOT_MINUTES = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeteoVeoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([RadarImage(hass, entry.runtime_data.home)])


def _slot(now: datetime) -> datetime:
    return now.replace(minute=now.minute - now.minute % SLOT_MINUTES, second=0, microsecond=0)


class RadarImage(CoordinatorEntity[HomeCoordinator], ImageEntity):
    """Radar of the last hour and the next, around the place."""

    _attr_has_entity_name = True
    entity_description = ImageEntityDescription(key="radar", translation_key="radar")

    def __init__(self, hass: HomeAssistant, coordinator: HomeCoordinator) -> None:
        super().__init__(coordinator)
        ImageEntity.__init__(self, hass)
        runtime = coordinator.config_entry.runtime_data
        self._attr_unique_id = f"{runtime.base_id}_radar"
        self._attr_device_info = runtime.device_info
        self._attr_content_type = "image/webp"
        self._attr_image_last_updated = _slot(dt_util.utcnow())
        self._image: bytes | None = None
        self._image_slot: datetime | None = None
        self._etag: str | None = None
        self._no_coverage = False

    @property
    def available(self) -> bool:
        return super().available and not self._no_coverage

    @callback
    def _handle_coordinator_update(self) -> None:
        # A new slot changes the state, so the frontend asks for the picture
        # again -- only if someone is looking.
        self._attr_image_last_updated = _slot(dt_util.utcnow())
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        slot = _slot(dt_util.utcnow())
        if self._image is not None and self._image_slot == slot:
            return self._image
        client = self.coordinator.client
        try:
            image, etag, content_type = await client.async_get_radar(
                self.coordinator.lang, etag=self._etag if self._image else None
            )
        except ApiError:
            # Outside radar coverage (or none right now): unavailable, not a
            # broken picture. The next state write shows it.
            self._no_coverage = True
            return None
        except MeteoVeoError:
            # Busy or unreachable: the previous picture is better than none.
            return self._image
        self._no_coverage = False
        if image is not None:
            self._image = image
            self._attr_content_type = content_type
        self._etag = etag
        self._image_slot = slot
        return self._image
