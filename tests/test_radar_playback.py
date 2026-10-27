"""Radar playback: the 1-24 hour loop as a camera, with a window select.

ADR-0866 D6. The one-hour `image` entity is untouched and stays free; this
is the Plus addition next to it. A camera rather than a second image,
because Home Assistant turns a camera into an MJPEG stream, which animates
in the phone app and full screen as well.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.meteoveo.client import ApiError, ServiceUnavailable
from custom_components.meteoveo.radar import (
    RADAR_EXTENTS,
    RADAR_WINDOWS,
    RadarView,
    extent_value,
    split_animation,
    window_hours,
)
from test_home_entities import ACCOUNT_DATA, setup
from test_plus_entities import free_view, plus_view

CAMERA = "camera.meteoveo_villa_ejemplo_radar_playback"
SELECT = "select.meteoveo_villa_ejemplo_radar_window"
EXTENT = "select.meteoveo_villa_ejemplo_radar_area"
RADAR_IMAGE = "image.meteoveo_villa_ejemplo_radar"
NOW = datetime(2026, 10, 23, 13, 5, tzinfo=timezone.utc)


def animated_webp(frames: int = 3, duration: int = 200) -> bytes:
    """A small animated WEBP, the shape the service answers with."""
    from PIL import Image

    pictures = [
        Image.new("RGB", (16, 12), (10 * index, 40, 200 - 10 * index))
        for index in range(frames)
    ]
    buffer = io.BytesIO()
    pictures[0].save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=pictures[1:],
        duration=duration,
        loop=0,
    )
    return buffer.getvalue()


WEBP = animated_webp()


def radar_answer(payload: bytes = WEBP):
    return AsyncMock(return_value=(payload, '"radar-1h"', "image/webp"))


def picture_url(hass: HomeAssistant) -> str:
    """The URL the frontend uses for the still picture (it carries the token)."""
    return hass.states.get(CAMERA).attributes["entity_picture"]


def stream_url(hass: HomeAssistant) -> str:
    return picture_url(hass).replace("/camera_proxy/", "/camera_proxy_stream/")


# --- The option list itself -------------------------------------------------


def test_the_windows_are_the_five_the_product_offers():
    assert RADAR_WINDOWS == ("1h", "3h", "6h", "12h", "24h")
    assert [window_hours(option) for option in RADAR_WINDOWS] == [1, 3, 6, 12, 24]
    # Anything else falls back to the free, always-served window.
    assert window_hours("48h") == 1
    assert window_hours("") == 1


def test_split_animation_yields_one_jpeg_per_frame():
    frames, seconds = split_animation(animated_webp(frames=4, duration=250))
    assert len(frames) == 4
    assert all(frame.startswith(b"\xff\xd8\xff") for frame in frames)
    assert seconds == pytest.approx(0.25, abs=0.01)


def test_split_animation_survives_a_single_frame_picture():
    frames, seconds = split_animation(animated_webp(frames=1))
    assert len(frames) == 1
    assert seconds > 0


def test_split_animation_returns_nothing_for_rubbish():
    # A proxy's error page must not take the camera down with a traceback.
    assert split_animation(b"not a picture at all") == ([], 0.2)


def test_the_shared_view_notifies_its_watchers():
    view = RadarView()
    seen: list[tuple[str, str]] = []
    remove = view.subscribe(lambda: seen.append((view.window, view.extent)))
    assert (view.window, view.hours, view.extent) == ("1h", 1, "local")
    view.choose_window("6h")
    view.choose_extent("spain")
    assert view.hours == 6 and view.extent == "spain"
    assert seen == [("6h", "local"), ("6h", "spain")]
    remove()
    view.choose_window("12h")
    assert len(seen) == 2


def test_the_areas_are_the_three_the_radar_can_show():
    assert RADAR_EXTENTS == ("local", "region", "spain")
    # Anything unknown degrades to the area the service serves at every
    # level, exactly as an unknown window degrades to one hour.
    assert extent_value("canarias") == "local"
    assert extent_value(None) == "local"


def test_choosing_an_area_clears_a_previous_refusal():
    view = RadarView()
    view.set_refused(True)
    view.choose_extent("region")
    assert view.refused is False


# --- Who gets the entities -------------------------------------------------


async def test_a_free_account_gets_neither_camera_nor_select(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA, home=free_view())
    assert hass.states.get(CAMERA) is None
    assert hass.states.get(SELECT) is None
    # And the free one-hour loop is exactly where it was.
    assert hass.states.get(RADAR_IMAGE) is not None


async def test_plus_gets_the_camera_and_the_select(hass: HomeAssistant) -> None:
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    registry = er.async_get(hass)

    assert registry.async_get(CAMERA).unique_id == f"{entry.unique_id}_radar_playback"
    # ADR-0833's image entity keeps its own unique id, so its history stands.
    assert registry.async_get(RADAR_IMAGE).unique_id == f"{entry.unique_id}_radar"

    select = registry.async_get(SELECT)
    assert select.entity_category is EntityCategory.CONFIG
    assert select.unique_id == f"{entry.unique_id}_radar_window"
    state = hass.states.get(SELECT)
    assert state.state == "1h"
    assert state.attributes["options"] == list(RADAR_WINDOWS)


async def test_the_camera_appears_when_plus_arrives(
    hass: HomeAssistant, mock_home_view
) -> None:
    entry = await setup(hass, ACCOUNT_DATA, home=free_view())
    assert hass.states.get(CAMERA) is None

    mock_home_view.return_value = (plus_view(), '"e2"')
    await entry.runtime_data.home.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(CAMERA) is not None
    assert hass.states.get(SELECT) is not None


async def test_losing_plus_makes_them_unavailable_not_gone(
    hass: HomeAssistant, mock_home_view
) -> None:
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    mock_home_view.return_value = (free_view(), '"e3"')
    await entry.runtime_data.home.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(CAMERA).state == "unavailable"
    assert hass.states.get(SELECT).state == "unavailable"
    ids = {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert {CAMERA, SELECT} <= ids


# --- The picture ------------------------------------------------------------


async def test_the_still_picture_is_the_animated_webp(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        # Nothing is fetched before someone looks.
        assert get.await_count == 0

        client = await hass_client()
        response = await client.get(picture_url(hass))
        assert response.status == 200
        assert response.headers["Content-Type"] == "image/webp"
        assert await response.read() == WEBP

        # Same ten-minute slot, same window: served from memory.
        await client.get(picture_url(hass))
        assert get.await_count == 1
        assert get.await_args.kwargs["window_hours"] == 1


async def test_choosing_a_window_asks_the_service_for_it(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))

        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": SELECT, "option": "6h"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert hass.states.get(SELECT).state == "6h"
        # The switch asks for the new loop at once, without waiting for the
        # next ten-minute slot.
        assert get.await_count == 2
        assert get.await_args.kwargs["window_hours"] == 6
        # A window change invalidates the conditional request: an ETag from
        # the one-hour loop says nothing about the six-hour one.
        assert get.await_args.kwargs["etag"] is None


async def test_the_chosen_window_survives_a_restart(hass: HomeAssistant) -> None:
    # ADR-0866 D6: the value is kept, so a dashboard does not snap back to
    # one hour every time Home Assistant restarts.
    mock_restore_cache(hass, (State(SELECT, "12h"),))
    await setup(hass, ACCOUNT_DATA, home=plus_view())
    assert hass.states.get(SELECT).state == "12h"
    entry = hass.config_entries.async_entries("meteoveo")[0]
    assert entry.runtime_data.radar_view.hours == 12


async def test_a_nonsense_restored_value_falls_back_to_one_hour(hass: HomeAssistant) -> None:
    mock_restore_cache(hass, (State(SELECT, "unavailable"),))
    await setup(hass, ACCOUNT_DATA, home=plus_view())
    assert hass.states.get(SELECT).state == "1h"


async def test_a_refused_long_window_is_unavailable_not_an_error_flood(
    hass: HomeAssistant, hass_client, freezer, caplog
) -> None:
    # Until the server side ships, window>1 answers 403 plus_required. That
    # must leave the entities unavailable and the log quiet -- not a
    # re-authentication prompt and not a message every ten minutes.
    freezer.move_to(NOW)
    get = AsyncMock(side_effect=ApiError(403, "plus_required"))
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))
        await hass.async_block_till_done()

        assert hass.states.get(CAMERA).state == "unavailable"
        assert hass.states.get(SELECT).state == "unavailable"
        assert caplog.text.count("plus_required") <= 1
        assert "ERROR" not in caplog.text


async def test_a_busy_service_keeps_the_previous_loop(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))

        freezer.tick(600)
        get.side_effect = ServiceUnavailable("busy")
        response = await client.get(picture_url(hass))
        assert response.status == 200
        assert await response.read() == WEBP


async def test_no_coverage_makes_the_camera_unavailable(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = AsyncMock(side_effect=ApiError(404, "no_place"))
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))
        await hass.async_block_till_done()
        assert hass.states.get(CAMERA).state == "unavailable"


# --- The MJPEG stream -------------------------------------------------------


async def test_the_camera_serves_an_mjpeg_stream_of_the_webp_frames(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    # This is the whole reason it is a camera: the phone app and full screen
    # play an MJPEG stream, while an animated WEBP depends on the browser.
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        response = await client.get(stream_url(hass))
        assert response.status == 200
        assert "multipart/x-mixed-replace" in response.headers["Content-Type"]
        chunk = await response.content.read(120)
        assert b"Content-Type: image/jpeg" in chunk
        response.close()


async def test_the_frames_are_split_off_the_event_loop(
    hass: HomeAssistant, freezer
) -> None:
    # Decoding an animation is blocking work; doing it in the loop would
    # stall everything else in Home Assistant for the duration.
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
        camera = next(
            entity
            for entity in hass.data["entity_components"]["camera"].entities
            if entity.entity_id == CAMERA
        )
        with patch.object(
            hass, "async_add_executor_job", wraps=hass.async_add_executor_job
        ) as executor:
            frames = await camera.async_frames()
        assert len(frames) == 3
        assert executor.called
        assert entry.runtime_data.radar_view.window == "1h"


async def test_the_camera_advertises_no_stream_feature(hass: HomeAssistant) -> None:
    # Without the "stream" integration a camera that advertises STREAM
    # cannot be played at all; MJPEG is what works everywhere, which is why
    # this is a camera in the first place.
    await setup(hass, ACCOUNT_DATA, home=plus_view())
    assert hass.states.get(CAMERA).attributes["supported_features"] == 0


async def test_a_station_key_entry_does_not_load_the_camera_platform(
    hass: HomeAssistant,
) -> None:
    # A station key has no account behind it, so it can never reach Plus --
    # and Home Assistant should not set up the camera and select components
    # for an entry that will never have one of their entities.
    from test_reauth_and_options import ENTRY_DATA, VIEW
    from unittest.mock import AsyncMock as _AsyncMock
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="meteoveo", data=ENTRY_DATA, unique_id="mvexample1")
    entry.add_to_hass(hass)
    with patch(
        "custom_components.meteoveo.client.MeteoVeoClient.async_get_station",
        new=_AsyncMock(return_value=VIEW),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert "camera" not in hass.config.components
    assert "select" not in hass.config.components
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_free_account_entry_still_loads_them(hass: HomeAssistant) -> None:
    # It may become Plus while Home Assistant runs, and then the entities
    # have to be able to appear without a restart.
    await setup(hass, ACCOUNT_DATA, home=free_view())
    assert "camera" in hass.config.components
    assert "select" in hass.config.components


# --- The area (ADR-0866 follow-up: the radar extent) -----------------------


async def test_plus_gets_the_area_select_too(hass: HomeAssistant) -> None:
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    registry = er.async_get(hass)
    select = registry.async_get(EXTENT)
    assert select.unique_id == f"{entry.unique_id}_radar_extent"
    assert select.entity_category is EntityCategory.CONFIG
    state = hass.states.get(EXTENT)
    assert state.state == "local"
    assert state.attributes["options"] == list(RADAR_EXTENTS)


async def test_a_free_account_gets_no_area_select(hass: HomeAssistant) -> None:
    await setup(hass, ACCOUNT_DATA, home=free_view())
    assert hass.states.get(EXTENT) is None


async def test_losing_plus_makes_the_area_select_unavailable(
    hass: HomeAssistant, mock_home_view
) -> None:
    entry = await setup(hass, ACCOUNT_DATA, home=plus_view())
    mock_home_view.return_value = (free_view(), '"e4"')
    await entry.runtime_data.home.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(EXTENT).state == "unavailable"
    assert EXTENT in {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }


async def test_the_default_area_is_not_sent_at_all(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    # "local" is the free area the service serves at every level, so the
    # request stays the one 0.2.1 makes: no extent parameter.
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))
        assert get.await_args.kwargs["extent"] == "local"


async def test_choosing_an_area_asks_the_service_for_it(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))

        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": EXTENT, "option": "spain"},
            blocking=True,
        )
        await hass.async_block_till_done()

        assert hass.states.get(EXTENT).state == "spain"
        assert get.await_count == 2
        assert get.await_args.kwargs["extent"] == "spain"
        # An ETag from the local view says nothing about the wide one.
        assert get.await_args.kwargs["etag"] is None


async def test_the_two_selects_describe_one_request(
    hass: HomeAssistant, hass_client, freezer
) -> None:
    freezer.move_to(NOW)
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        for entity_id, option in ((SELECT, "6h"), (EXTENT, "spain")):
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": option},
                blocking=True,
            )
        await hass.async_block_till_done()
        await client.get(picture_url(hass))

        kwargs = get.await_args.kwargs
        assert (kwargs["window_hours"], kwargs["extent"]) == (6, "spain")


async def test_the_chosen_area_survives_a_restart(hass: HomeAssistant) -> None:
    mock_restore_cache(hass, (State(EXTENT, "region"),))
    await setup(hass, ACCOUNT_DATA, home=plus_view())
    assert hass.states.get(EXTENT).state == "region"
    entry = hass.config_entries.async_entries("meteoveo")[0]
    assert entry.runtime_data.radar_view.extent == "region"


async def test_a_nonsense_restored_area_falls_back_to_local(hass: HomeAssistant) -> None:
    mock_restore_cache(hass, (State(EXTENT, "canarias"),))
    await setup(hass, ACCOUNT_DATA, home=plus_view())
    assert hass.states.get(EXTENT).state == "local"


async def test_a_rejected_area_keeps_the_last_loop_and_is_said_once(
    hass: HomeAssistant, hass_client, freezer, caplog, mock_home_view
) -> None:
    # 400 bad_extent is our own bug, not the user's: the picture they have
    # stays, and the log says it once rather than on every look.
    freezer.move_to(NOW)
    mock_home_view.return_value = (plus_view(), '"e"')
    get = radar_answer()
    with patch("custom_components.meteoveo.client.MeteoVeoClient.async_get_radar", new=get):
        await setup(hass, ACCOUNT_DATA, home=plus_view())
        client = await hass_client()
        await client.get(picture_url(hass))

        get.side_effect = ApiError(400, "bad_extent")
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": EXTENT, "option": "region"},
            blocking=True,
        )
        await hass.async_block_till_done()
        for _ in range(3):
            response = await client.get(picture_url(hass))
        await hass.async_block_till_done()

        # Still there, still the previous loop.
        assert hass.states.get(EXTENT).state == "region"
        assert hass.states.get(CAMERA).state != "unavailable"
        assert response.status == 200
        assert await response.read() == WEBP
        assert caplog.text.count("bad_extent") == 1
        assert "ERROR" not in caplog.text
