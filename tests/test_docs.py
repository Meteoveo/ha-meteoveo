"""Knowledge-base pages.

The config flow links to documentation pages on GitHub. A link that points at
a page that does not exist in the repository is worse than no link -- it is a
404 shown to someone who is already stuck.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.meteoveo import const

REPO = Path(__file__).resolve().parents[1]

DOC_URLS = [
    const.DOCS_SETUP_URL,
    const.DOCS_MEASUREMENTS_URL,
    const.DOCS_RECIPROCITY_URL,
    const.DOCS_TROUBLESHOOTING_URL,
]


@pytest.mark.parametrize("url", DOC_URLS)
def test_every_linked_docs_page_exists_in_the_repo(url):
    # blob/main/docs/<page>.md -> docs/<page>.md
    match = re.search(r"/blob/main/(docs/[\w-]+\.md)$", url)
    assert match, url
    page = REPO / match.group(1)
    assert page.is_file(), page
    assert len(page.read_text(encoding="utf-8")) > 200, "page is a stub"


def test_docs_pages_do_not_leak_internals():
    # This repository is public. The docs must not mention internal hostnames,
    # server paths or live station ids.
    forbidden = re.compile(
        r"(/opt/meteoveo|hetzner|178\.105|MV(?!EXAMPLE)[0-9A-Z]{8})"
    )
    for page in (REPO / "docs").glob("*.md"):
        text = page.read_text(encoding="utf-8")
        assert not forbidden.search(text), page.name


def test_manifest_documentation_points_at_this_repo():
    manifest = json.loads(
        (REPO / "custom_components/meteoveo/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["documentation"].startswith("https://github.com/meteoveo/ha-meteoveo")


def test_readme_links_every_docs_page():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    for page in ("setup", "measurements", "probability", "reciprocity", "troubleshooting"):
        assert f"docs/{page}.md" in readme, page


# --- ADR-0866 D2: what Plus adds, and where it is visible ------------------
#
# The feature list lives here and nowhere else. The service decides who gets
# what; this page is the only place that *names* it, so it is also the only
# place that can go stale -- hence these checks.


def readme() -> str:
    return (REPO / "README.md").read_text(encoding="utf-8")


def test_the_readme_has_the_plus_section_in_two_columns():
    text = readme()
    assert "### Plus — and what a station unlocks" in text
    # Both columns of the table exist, so "where do I see it" is answered.
    assert "In Home Assistant" in text and "In the MeteoVeo app and on the web" in text
    # The level sensor is how Home Assistant shows it.
    assert "**Level** sensor" in text
    # The orphan sentence this section replaces is gone.
    assert "sees its Plus level in Home Assistant as well" not in text


def test_the_readme_says_the_one_hour_loop_stays_free():
    # ADR-0866 D6: a released feature is not taken away. Someone reading the
    # table must not conclude that the radar they already have became paid.
    text = readme()
    assert "stays free for everyone" in text


def test_the_forecast_map_row_stays_commented_out():
    # ADR-0620 D5/D8: it may only be listed once the server serves it to the
    # premium audience. Until then the row is there, but not published.
    text = readme()
    start = text.index("<!-- Add only once FORECAST_MAP_AUDIENCE=premium")
    end = text.index("-->", start)
    assert "Animated 24-hour forecast map" in text[start:end]
    assert text.count("Animated 24-hour forecast map") == 1


def test_the_station_extras_are_not_called_a_plus_feature():
    # ADR-0866 D2: two different things (reciprocity extras vs the paid
    # level) that must not blur into one.
    text = readme()
    assert "## A station that stops reporting" in text


def test_reciprocity_states_that_a_station_grants_plus():
    text = (REPO / "docs/reciprocity.md").read_text(encoding="utf-8")
    assert "**MeteoVeo Plus**" in text
    assert "A subscription is never needed for it" in text


def test_the_setup_guide_mentions_plus_at_the_station_question():
    text = (REPO / "docs/setup.md").read_text(encoding="utf-8")
    assert "MeteoVeo Plus in the app and on the web" in text
    assert "[reciprocity](reciprocity.md)" in text


def test_the_card_page_explains_the_radar_playback_camera():
    text = (REPO / "docs/card.md").read_text(encoding="utf-8")
    assert "### The 24-hour radar on a dashboard" in text
    assert "camera.meteoveo_<town>_radar_playback" in text
    assert "camera_view: live" in text
    # The card itself is unchanged -- it keeps the free one-hour local loop.
    assert "keeps showing the one-hour" in text
    # The area is settable too, with the three steps named.
    assert "**Radar area**" in text
    for step in ("Around the town", "Region", "Peninsula and Balearics"):
        assert step in text, step
    # And it does not promise a radar over the Canaries, where we measure
    # nothing at all.
    assert "no Canary Islands area" in text


def test_the_readme_points_at_the_radar_playback_section():
    assert "docs/card.md#the-24-hour-radar-on-a-dashboard" in readme()


def test_the_readme_names_the_radar_area_without_promising_the_canaries():
    text = readme()
    assert "**Radar area**" in text
    assert "Peninsula and Balearics" in text
    # Nowhere does the radar row offer the Canaries.
    radar_row = next(line for line in text.splitlines() if "Radar playback" in line and "|" in line)
    assert "Canar" not in radar_row


# --- Issue #1: what the daily percentage means -----------------------------


def test_the_probability_page_says_what_the_percentage_is() -> None:
    text = (REPO / "docs/probability.md").read_text(encoding="utf-8")
    assert len(text) > 200
    # The threshold the figure is about, and whose figure it is.
    assert "0.2 mm" in text
    assert "not the same number" in text and "AEMET" in text
    # The question the issue actually asked.
    assert "same percentage" in text


def test_the_probability_page_keeps_the_internals_internal() -> None:
    # The repository is public. How the figure is calibrated, against what,
    # and how well, is not published -- the page says what the number means.
    text = (REPO / "docs/probability.md").read_text(encoding="utf-8")
    for internal in ("Brier", "ADR-", "precipProbBasis", "lead", "%,", "calibrat"):
        assert internal not in text, internal


def test_the_card_page_documents_the_three_source_positions() -> None:
    text = (REPO / "docs/card.md").read_text(encoding="utf-8")
    assert "`attribution`" in text
    for position in ("`compact`", "`full`", "`off`"):
        assert position in text, position
    # And why it can be switched off without the naming being lost.
    assert "licence obligation" in text
    assert "configuration panel" in text
