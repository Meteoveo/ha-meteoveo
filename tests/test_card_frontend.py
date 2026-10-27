"""The bundled card's own behaviour (issue #2: the source footer).

The card is a plain ES module, so its logic is tested with ``node --test``.
Those tests ran nowhere automatically until now; this module runs them inside
the Python suite, and checks the handful of invariants that must hold whether
or not Node is on the machine.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from test_home_entities import ACCOUNT_DATA, WEATHER, setup

REPO = Path(__file__).resolve().parents[1]
CARD = REPO / "custom_components/meteoveo/frontend/meteoveo-card.js"
CARD_TESTS = REPO / "tools/card-preview/card.test.mjs"


def card_source() -> str:
    return CARD.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_the_cards_own_test_suite_passes() -> None:
    finished = subprocess.run(
        ["node", "--test", str(CARD_TESTS)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr


def test_the_source_footer_is_folded_by_default() -> None:
    # The complaint was six grey lines on a panel. One line is the default;
    # `full` is the card as it was, and nobody is upgraded into a change
    # they did not ask for beyond this one.
    assert 'attribution: "compact"' in card_source()


def test_the_footer_has_exactly_three_positions() -> None:
    source = card_source()
    assert '["compact", "full", "off"]' in source
    for position in ("compact", "full", "off"):
        assert f"{position}:" in source


def test_the_editor_ends_with_the_full_notice_and_a_reason() -> None:
    # Naming the sources is a licence obligation, so there is one place that
    # cannot be switched off. It is the last thing in the form.
    source = card_source()
    tail = source[source.index('name: "attribution_sources"') :]
    assert "MeteoVeoCard.fullAttribution()" in tail
    assert 'name: "attribution_licence"' in tail
    # Nothing else is added after it.
    assert tail.index('name: "attribution_licence"') < tail.index("],")


def test_every_language_names_the_sources_the_same_way() -> None:
    source = card_source()
    for short in (
        "Datos: AEMET · MeteoVeo",
        "Data: AEMET · MeteoVeo",
        "Dades: AEMET · MeteoVeo",
        "Adatok: AEMET · MeteoVeo",
    ):
        assert f'attributionShort: "{short}"' in source


def test_the_hourly_row_says_that_it_scrolls() -> None:
    # The report: the last hour is cut off at the card's edge, which reads as
    # a rendering fault. The row did scroll -- nothing said so. A fading edge,
    # a snap and two chevrons say it.
    source = card_source()
    assert "scroll-snap-type: x proximity" in source
    assert "scroll-snap-align: start" in source
    assert ".can-right .scroll { --fade-r:" in source
    assert 'class="nav prev"' in source and 'class="nav next"' in source


def test_the_scroll_position_survives_a_refresh() -> None:
    # The card re-renders on every state change; without this the row jumps
    # back to "now" under the viewer's finger every few minutes.
    source = card_source()
    assert "this._hourScroll = previous.scrollLeft" in source
    assert "_wireHourly()" in source


def test_a_full_day_of_hours_is_the_default() -> None:
    source = card_source()
    assert "hourly_count: 24" in source
    assert 'name: "hourly_count", default: 24' in source


def test_the_next_hours_block_can_be_conditional() -> None:
    # The second suggestion: show it only when there is rain to show.
    source = card_source()
    assert 'next_hour_when: "always"' in source
    assert 'this._config.next_hour_when === "rain" && !nextHourHasRain(model)' in source
    assert '["always", "rain"]' in source


def test_every_language_names_the_new_option() -> None:
    source = card_source()
    for key in ("next_hour_when:", "next_hour_when_options:", "hoursPrev:", "hoursNext:"):
        assert source.count(key) >= 4, key


def test_the_card_version_matches_the_integration() -> None:
    manifest = json.loads(
        (REPO / "custom_components/meteoveo/manifest.json").read_text(encoding="utf-8")
    )
    assert f'export const CARD_VERSION = "{manifest["version"]}";' in card_source()


async def test_the_entity_still_carries_the_full_attribution(hass: HomeAssistant) -> None:
    # Whatever the card is told to show, the licence footing stands: Home
    # Assistant's own place for it is the entity attribute, and hiding the
    # footer must not touch it.
    await setup(hass, ACCOUNT_DATA)
    assert hass.states.get(WEATHER).attributes["attribution"] == "Datos: © AEMET, MeteoVeo."
