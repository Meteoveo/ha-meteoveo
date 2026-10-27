"""Radar playback as a camera entity (ADR-0866 D6).

The service renders the loop as an animated WEBP over 1, 3, 6, 12 or 24
hours, around the town or over a wider area. A camera rather than a second
``image`` entity for one reason: Home
Assistant turns a camera into an **MJPEG** stream, which plays in the phone
app and in full screen, while an animated WEBP relies on the browser doing
it. The still picture is still the WEBP itself, so a dashboard thumbnail
animates too where the browser can.

The one-hour loop stays free as the ``image`` entity (ADR-0833) and keeps its
own unique id -- nothing here touches it.
"""

from __future__ import annotations

import logging
from datetime import datetime

from aiohttp import web
from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    async_get_still_stream,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .client import ApiError, MeteoVeoError
from .coordinator import HomeCoordinator, MeteoVeoConfigEntry
from .entity import add_when_allowed
from .home import has_plus
from .radar import (
    DEFAULT_FRAME_SECONDS,
    RadarView,
    radar_slot,
    split_animation,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

#: The service's own refusal when a long window or a wide area is asked for
#: without Plus.
PLUS_REQUIRED = "plus_required"

#: An area the service does not know. Our selects only offer the three it
#: does, so this can only be our own bug or a hand-edited state.
BAD_EXTENT = "bad_extent"


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
        platform="camera",
        unique_id=f"{runtime.base_id}_radar_playback",
        allowed=has_plus,
        build=lambda: [RadarPlaybackCamera(runtime.home, runtime.radar_view)],
    )


class RadarPlaybackCamera(CoordinatorEntity[HomeCoordinator], Camera):
    """The radar loop over the chosen window and area, around the entry's place.

    Fetched only when someone looks, and at most once per ten-minute radar
    slot per view -- the same economy as the free one-hour image.
    """

    _attr_has_entity_name = True
    entity_description = CameraEntityDescription(
        key="radar_playback", translation_key="radar_playback"
    )

    def __init__(self, coordinator: HomeCoordinator, view: RadarView) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        runtime = coordinator.config_entry.runtime_data
        self._attr_unique_id = f"{runtime.base_id}_radar_playback"
        self._attr_device_info = runtime.device_info
        # A plain attribute on Camera, not an _attr_ property: the still
        # picture is the animated WEBP itself, so a browser that can play it
        # animates the dashboard thumbnail as well.
        self.content_type = "image/webp"
        self._attr_frame_interval = DEFAULT_FRAME_SECONDS
        self._view = view
        self._animation: bytes | None = None
        self._frames: list[bytes] = []
        self._frame_seconds = DEFAULT_FRAME_SECONDS
        self._etag: str | None = None
        self._slot: datetime | None = None
        self._rendered: tuple[str, str] | None = None
        #: Views the service answered ``bad_extent`` for. Asking again would
        #: only repeat the same mistake, and the same log line.
        self._rejected: set[tuple[str, str]] = set()
        self._no_coverage = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._view.subscribe(self._handle_view_change))

    @property
    def available(self) -> bool:
        # Three ways to be unavailable, none of them an error: the level fell
        # back, the service says this window is not ours, or the place has no
        # radar. A free account never gets this entity in the first place.
        return (
            super().available
            and has_plus(self.coordinator.data)
            and not self._view.refused
            and not self._no_coverage
        )

    @callback
    def _handle_view_change(self) -> None:
        """A new window or area was chosen: drop the old loop, fetch the new one.

        The ETag goes with it -- an ETag from the one-hour local loop says
        nothing about the six-hour or the peninsula one, and sending it
        would invite a 304 for a picture we do not have.

        The previous loop is kept until the new one arrives, because a
        rejected area (``bad_extent``) must leave the viewer with the
        picture they had rather than with a blank card.
        """
        self._frames = []
        self._etag = None
        self._rendered = None
        self._no_coverage = False
        self.async_write_ha_state()
        if self.hass is not None and not self._view.refused:
            # Asked for at once rather than at the next slot: the point of
            # the switches is that the picture changes when you flip them.
            self.hass.async_create_task(self._async_load())

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """The animated WEBP. Width and height are ignored: the server frames it."""
        await self._async_load()
        return self._animation

    async def async_frames(self) -> list[bytes]:
        """The loop as JPEG frames, decoded off the event loop."""
        await self._async_load()
        if self._animation is None:
            return []
        if not self._frames:
            frames, seconds = await self.hass.async_add_executor_job(
                split_animation, self._animation
            )
            self._frames = frames
            self._frame_seconds = seconds
            self._attr_frame_interval = seconds
        return self._frames

    async def handle_async_mjpeg_stream(self, request: web.Request) -> web.StreamResponse | None:
        """Play the loop as MJPEG, one WEBP frame per MJPEG frame.

        Home Assistant's own still-stream helper would call
        :meth:`async_camera_image` over and over and send the same animation
        every time; the viewer would see a single picture. Feeding it the
        frames instead is what makes the phone app animate.
        """
        frames = await self.async_frames()
        if not frames:
            return None
        state: dict[str, object] = {"frames": frames, "index": 0}

        async def _next_frame() -> bytes | None:
            index = int(state["index"])
            current: list[bytes] = state["frames"]  # type: ignore[assignment]
            if index >= len(current):
                # The loop restarted: pick up a newer radar run, or a new
                # window, without the viewer reopening the stream.
                current = await self.async_frames()
                if not current:
                    return None
                state["frames"] = current
                index = 0
            state["index"] = index + 1
            return current[index]

        return await async_get_still_stream(
            request, _next_frame, "image/jpeg", self._frame_seconds
        )

    async def _async_load(self) -> None:
        """Make sure the current slot's loop for the current view is at hand."""
        slot = radar_slot(dt_util.utcnow())
        view = (self._view.window, self._view.extent)
        if self._animation is not None and self._slot == slot and self._rendered == view:
            return
        if self._view.refused or view in self._rejected:
            return

        try:
            animation, etag, _ = await self.coordinator.client.async_get_radar(
                self.coordinator.lang,
                etag=self._etag if self._rendered == view else None,
                window_hours=self._view.hours,
                extent=self._view.extent,
            )
        except ApiError as failure:
            if failure.code == PLUS_REQUIRED:
                # The level changed under us (or a server rollback). The
                # entities go unavailable, and it is said once at debug
                # level -- not a message every ten minutes.
                _LOGGER.debug(
                    "the service refused the %s/%s radar view (%s)",
                    *view,
                    PLUS_REQUIRED,
                )
                self._view.set_refused(True)
                self._animation = None
                self._frames = []
            elif failure.code == BAD_EXTENT:
                # Our bug, not the user's: remember it so it is asked once,
                # and leave them the picture they already have.
                _LOGGER.debug("the service does not know the %s radar area (%s)",
                              view[1], BAD_EXTENT)
                self._rejected.add(view)
            else:
                # 404 no_place / disabled: outside coverage.
                self._no_coverage = True
                self._animation = None
                self._frames = []
            self._write_state()
            return
        except MeteoVeoError:
            # Busy, render failed, unreachable: the previous loop is better
            # than no loop, and the next look tries again.
            return

        self._no_coverage = False
        self._view.set_refused(False)
        if animation is not None:
            self._animation = animation
            self._frames = []
        self._etag = etag
        self._slot = slot
        self._rendered = view

    @callback
    def _write_state(self) -> None:
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()
