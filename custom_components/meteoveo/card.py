"""Serving the bundled Lovelace card.

The card ships inside the integration, so one HACS install brings both and the
card needs no separate review or resource entry. It is registered once per
Home Assistant start, and only when the file is actually present.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import VERSION

_LOGGER = logging.getLogger(__name__)

CARD_URL = "/meteoveo/meteoveo-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "meteoveo-card.js"


def card_cache_tag(card_file: Path, version: str = VERSION) -> str:
    """The query string that makes a browser fetch the card again.

    The version alone is not enough. The static path is served with a long
    cache lifetime, and the frontend's service worker caches the URL as well,
    so a card that changes WITHOUT a version bump keeps serving from the cache
    - the browser never learns. That cost us a wrong diagnosis twice: once a
    stale card looked like a "configuration error", and once an option that was
    already shipped looked missing.

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


async def async_register_card(hass: HomeAssistant, card_file: Path = CARD_FILE) -> bool:
    """Serve the card and load it in every dashboard. Returns whether it did."""
    # A file-system check is blocking I/O; it runs in the executor.
    if not await hass.async_add_executor_job(card_file.is_file):
        _LOGGER.debug("card not bundled; skipping its registration")
        return False
    if hass.http is None:
        # No web server (a bare test instance): nothing to serve from.
        return False

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_file), cache_headers=True)]
    )
    # The version AND the file's fingerprint (see `card_cache_tag`): an update
    # and a changed-but-same-version card both get a fresh URL, while an
    # unchanged card keeps its long cache lifetime.
    tag = await hass.async_add_executor_job(card_cache_tag, card_file)
    add_extra_js_url(hass, f"{CARD_URL}?v={tag}")
    return True
