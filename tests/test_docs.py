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
    for page in ("setup", "measurements", "reciprocity", "troubleshooting"):
        assert f"docs/{page}.md" in readme, page
