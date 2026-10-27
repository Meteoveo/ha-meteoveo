"""Serving the bundled Lovelace card.

The card ships inside the integration, so one HACS install brings both and the
card needs no separate review or resource entry. It is registered once per
Home Assistant start, and only when the file is actually present.

The card is served by a view of our own rather than as a static path, so that
a card that changed on disk reaches the browser on a reload -- without a Home
Assistant restart. See `MeteoVeoCardView`.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from aiohttp import hdrs, web

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import VERSION

_LOGGER = logging.getLogger(__name__)

CARD_URL = "/meteoveo/meteoveo-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "meteoveo-card.js"


def card_cache_tag(card_file: Path, version: str = VERSION) -> str:
    """The query string that makes a browser fetch the card again.

    The version alone is not enough. The frontend's service worker caches the
    URL, so a card that changes WITHOUT a version bump can keep serving from
    the cache - the browser never learns. That cost us a wrong diagnosis twice:
    once a stale card looked like a "configuration error", and once an option
    that was already shipped looked missing.

    The fix is the file's own fingerprint: eight hex characters of its sha256
    appended to the version. Same file, same URL (the cache still works between
    updates); changed file, new URL.
    """
    try:
        digest = hashlib.sha256(card_file.read_bytes()).hexdigest()[:8]
    except OSError:
        # Unreadable file: the version alone is still better than nothing, and
        # the caller has already checked that the file exists.
        return version
    return f"{version}-{digest}"


class MeteoVeoCardView(HomeAssistantView):
    """The card file itself, served so that it can change under a running HA.

    A static path (`StaticPathConfig(..., cache_headers=True)`) is served with
    a year-long, immutable cache lifetime. That is right for a file whose name
    carries its content, and wrong for this one: the URL is decided when Home
    Assistant starts, so after an update the browser keeps asking for the old
    address -- and answers it from its own cache -- until Home Assistant is
    restarted. The card then looked unchanged to everyone, twice.

    This view sends the file with `Cache-Control: no-cache`: the browser may
    keep its copy, but it has to ask every time whether it is still current,
    and aiohttp answers that from the file's own mtime and size (304, no body).
    A card-only update therefore needs a browser reload, not a restart.
    """

    url = CARD_URL
    name = "meteoveo:card"
    requires_auth = False

    def __init__(self, card_file: Path) -> None:
        """Keep the file this view serves."""
        self._card_file = card_file

    async def get(self, request: web.Request) -> web.StreamResponse:
        """Serve the card, revalidated on every load."""
        return web.FileResponse(
            self._card_file,
            headers={
                hdrs.CACHE_CONTROL: "no-cache",
                # Guessing the type from the name gives `text/plain` on some
                # systems, and a module served as text is not executed.
                hdrs.CONTENT_TYPE: "application/javascript; charset=utf-8",
            },
        )


async def async_register_card(hass: HomeAssistant, card_file: Path = CARD_FILE) -> bool:
    """Serve the card and load it in every dashboard. Returns whether it did."""
    # A file-system check is blocking I/O; it runs in the executor.
    if not await hass.async_add_executor_job(card_file.is_file):
        _LOGGER.debug("card not bundled; skipping its registration")
        return False
    if hass.http is None:
        # No web server (a bare test instance): nothing to serve from.
        return False

    hass.http.register_view(MeteoVeoCardView(card_file))
    # The version AND the file's fingerprint (see `card_cache_tag`): after a
    # restart an updated card is a different address, so not even a cache that
    # ignores `no-cache` (a service worker, a proxy) can hold the old one back.
    tag = await hass.async_add_executor_job(card_cache_tag, card_file)
    add_extra_js_url(hass, f"{CARD_URL}?v={tag}")
    return True
