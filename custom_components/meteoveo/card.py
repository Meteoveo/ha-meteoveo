"""Serving the bundled Lovelace card.

The card ships inside the integration, so one HACS install brings both and the
card needs no separate review or resource entry. It is registered once per
Home Assistant start, and only when the file is actually present.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import VERSION

_LOGGER = logging.getLogger(__name__)

CARD_URL = "/meteoveo/meteoveo-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "meteoveo-card.js"


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
    # The version in the query string makes browsers fetch the new card after
    # an update, while the long cache lifetime still applies between updates.
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    return True
