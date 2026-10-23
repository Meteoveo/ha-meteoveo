"""The radar loop as an image entity (ADR-0833 R4).

The picture is fetched only when Home Assistant asks for it (someone views
it), at most once per ten-minute radar slot; outside coverage the entity is
unavailable rather than showing a broken image.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.meteoveo.client import ApiError, ServiceUnavailable
from test_home_entities import ACCOUNT_DATA, setup

RADAR = "image.meteoveo_villa_ejemplo_radar"
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 example"
NOW = datetime(2026, 10, 23, 13, 5, tzinfo=timezone.utc)


async def test_radar_image_is_fetched_when_viewed(hass: HomeAssistant, hass_client, freezer) -> None:
    freezer.move_to(NOW)
    get = AsyncMock(return_value=(WEBP, '"radar-202610231300-es-a"', "image/webp"))
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA)
        # Setting up does not fetch: nobody is looking yet.
        assert get.await_count == 0
        state = hass.states.get(RADAR)
        assert state is not None and state.state == "2026-10-23T13:00:00+00:00"

        client = await hass_client()
        response = await client.get(state.attributes["entity_picture"])
        assert response.status == 200
        assert response.headers["Content-Type"] == "image/webp"
        assert await response.read() == WEBP
        # The same slot again: served from memory.
        await client.get(state.attributes["entity_picture"])
        assert get.await_count == 1


async def test_radar_unavailable_outside_coverage(hass: HomeAssistant, hass_client, freezer) -> None:
    freezer.move_to(NOW)
    get = AsyncMock(side_effect=ApiError(404, "no_coverage"))
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA)
        client = await hass_client()
        await client.get(hass.states.get(RADAR).attributes["entity_picture"])
        await hass.async_block_till_done()
        # The next state write reflects it.
        entry = hass.config_entries.async_entries("meteoveo")[0]
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(RADAR).state == "unavailable"


async def test_radar_keeps_the_last_picture_when_the_service_is_busy(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = AsyncMock(return_value=(WEBP, '"e1"', "image/webp"))
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA)
        client = await hass_client()
        await client.get(hass.states.get(RADAR).attributes["entity_picture"])
        # Next slot: the service is busy -> the previous picture stays.
        freezer.tick(600)
        get.side_effect = ServiceUnavailable("busy")
        entry = hass.config_entries.async_entries("meteoveo")[0]
        await entry.runtime_data.home.async_refresh()
        await hass.async_block_till_done()
        response = await client.get(hass.states.get(RADAR).attributes["entity_picture"])
        assert response.status == 200
        assert await response.read() == WEBP
