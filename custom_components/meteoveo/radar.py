"""The radar playback window, and turning an animated WEBP into frames.

ADR-0866 D6. The service renders the loop; Home Assistant only chooses how
far back it should reach and plays what comes back. Two things live here, both
free of Home Assistant so they can be tested on their own:

* :class:`RadarWindow` -- the chosen window, shared by the ``select`` that
  sets it and the ``camera`` that renders it.
* :func:`split_animation` -- the animation taken apart into JPEG frames for
  the MJPEG stream. It decodes pictures, so it is **blocking**: callers run
  it in an executor, never in the event loop.
"""

from __future__ import annotations

import io
import logging
import statistics
from datetime import datetime
from typing import Callable, Final

_LOGGER = logging.getLogger(__name__)

#: The windows the product offers. ``1h`` is the free loop everyone has as
#: the ``image`` entity; the rest need Plus (ADR-0866 D6/D8).
RADAR_WINDOWS: Final[tuple[str, ...]] = ("1h", "3h", "6h", "12h", "24h")

DEFAULT_RADAR_WINDOW: Final = "1h"

#: The service renders a new loop when a new radar frame is usable.
SLOT_MINUTES: Final = 10

#: Used when the animation does not say how long a frame lasts.
DEFAULT_FRAME_SECONDS: Final = 0.2

#: A 24-hour window is about 145 ten-minute frames; the cap is there so a
#: surprising answer cannot fill memory with decoded pictures.
MAX_FRAMES: Final = 400


def window_hours(option: str | None) -> int:
    """Hours behind the ``select`` option.

    Anything unknown falls back to one hour -- the window the service serves
    at every level, so a stale or hand-edited value degrades to the free
    loop instead of to an error.
    """
    if option in RADAR_WINDOWS:
        return int(str(option)[:-1])
    return 1


def radar_slot(now: datetime) -> datetime:
    """The ten-minute slot ``now`` belongs to."""
    return now.replace(
        minute=now.minute - now.minute % SLOT_MINUTES, second=0, microsecond=0
    )


class RadarWindow:
    """How far back the playback reaches, shared inside one config entry.

    The ``select`` entity owns the value and the ``camera`` renders it, so
    one of them has to hold it and the other has to hear about a change.
    ``refused`` carries the one other piece of shared news: the service
    answered that this account may not have a long window, which makes both
    entities unavailable rather than broken (ADR-0866 D8).
    """

    def __init__(self, option: str = DEFAULT_RADAR_WINDOW) -> None:
        self._option = option if option in RADAR_WINDOWS else DEFAULT_RADAR_WINDOW
        self._refused = False
        self._listeners: list[Callable[[], None]] = []

    @property
    def option(self) -> str:
        return self._option

    @property
    def hours(self) -> int:
        return window_hours(self._option)

    @property
    def refused(self) -> bool:
        """Whether the service refused this window as not available to the account."""
        return self._refused

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for a change; the return value removes it."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def choose(self, option: str) -> None:
        """Set the window. Unknown values are ignored, not stored."""
        if option not in RADAR_WINDOWS or option == self._option:
            return
        self._option = option
        # A new window is a new question for the service, so a previous
        # refusal says nothing about it.
        self._refused = False
        self._notify()

    def restore(self, option: str | None) -> None:
        """Take a value back from the state machine after a restart."""
        if option in RADAR_WINDOWS:
            self._option = str(option)

    def set_refused(self, refused: bool) -> None:
        if refused == self._refused:
            return
        self._refused = refused
        self._notify()

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()


def split_animation(animation: bytes) -> tuple[list[bytes], float]:
    """Split an animated WEBP into JPEG frames and the frame duration.

    **Blocking**: decodes every frame. Run it in an executor.

    Returns ``([], DEFAULT_FRAME_SECONDS)`` for anything that is not a
    picture -- a proxy's error page must not take the camera down with a
    traceback, and the still image is still served from the original bytes.
    """
    try:
        from PIL import Image, ImageSequence
    except ImportError:  # pragma: no cover - Pillow ships with Home Assistant
        _LOGGER.debug("Pillow is unavailable; the radar camera serves stills only")
        return [], DEFAULT_FRAME_SECONDS

    frames: list[bytes] = []
    durations: list[float] = []
    try:
        with Image.open(io.BytesIO(animation)) as picture:
            for frame in ImageSequence.Iterator(picture):
                duration = frame.info.get("duration")
                if isinstance(duration, (int, float)) and duration > 0:
                    durations.append(duration / 1000)
                buffer = io.BytesIO()
                frame.convert("RGB").save(buffer, format="JPEG", quality=80)
                frames.append(buffer.getvalue())
                if len(frames) >= MAX_FRAMES:
                    break
    except Exception as failure:  # noqa: BLE001 - any decode problem is the same
        _LOGGER.debug("could not split the radar loop: %s", type(failure).__name__)
        return [], DEFAULT_FRAME_SECONDS

    seconds = statistics.median(durations) if durations else DEFAULT_FRAME_SECONDS
    # Keep it inside something a browser can follow: a 20 ms frame would be
    # a flicker, a 5 s one would look stuck.
    return frames, min(2.0, max(0.1, seconds))
