"""The shipped blueprints (ADR-0935).

A blueprint is the only part of this repository that nothing else loads: it is
parsed by Home Assistant, in the user's instance, after an import from a "My"
button. A typo in the import URL or a dropped input is invisible here and
obvious there, so the structure, the self-referencing ``source_url`` and the
README's import buttons are checked from the files themselves.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
BLUEPRINTS = REPO / "blueprints/automation/meteoveo"
RAW_BASE = "https://github.com/Meteoveo/ha-meteoveo/blob/main/blueprints/automation/meteoveo"

#: The AEMET Meteoalerta codes, mirroring the service's own table
#: (services/api/src/forecast/warning-sentence.ts).
CANONICAL = {"PR", "TO", "VI", "NE", "CA", "BF", "CO", "NI", "DP", "AL", "PO"}


class Loader(yaml.SafeLoader):
    """Home Assistant's YAML tags (``!input``, ``!include``) kept as markers."""


Loader.add_multi_constructor("!", lambda loader, suffix, node: f"!{suffix}")


def files() -> list[Path]:
    return sorted(BLUEPRINTS.glob("*.yaml"))


def load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)


def readme() -> str:
    return (REPO / "README.md").read_text(encoding="utf-8")


def test_there_are_blueprints_to_check() -> None:
    # Guards the walks below: an empty glob would make every one of them pass.
    assert len(files()) >= 6


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_blueprint_parses_and_is_named(path: Path) -> None:
    data = load(path)
    meta = data["blueprint"]
    assert meta["domain"] == "automation"
    assert meta["name"].startswith("MeteoVeo")
    assert len(meta["description"].strip()) > 80
    # Every blueprint has a trigger; "triggers" is the current spelling.
    assert data.get("triggers"), path.name


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_blueprint_points_at_its_own_file(path: Path) -> None:
    # A source_url copied from a sibling makes Home Assistant offer the wrong
    # update, silently replacing one automation's blueprint with another's.
    assert load(path)["blueprint"]["source_url"] == f"{RAW_BASE}/{path.name}"


@pytest.mark.parametrize("path", files(), ids=lambda p: p.stem)
def test_every_blueprint_has_an_import_button_in_the_readme(path: Path) -> None:
    # The My button is half of the discoverability; a blueprint nobody can
    # find in one click is a file in a repository.
    quoted = f"{RAW_BASE}/{path.name}".replace(":", "%3A").replace("/", "%2F")
    assert quoted in readme(), path.name


def test_the_readme_counts_the_blueprints_it_lists() -> None:
    counts = {5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}
    assert f"{counts[len(files())]} ready-made automations" in readme()


# --- ADR-0935: the warning blueprints -------------------------------------


def test_the_new_blueprint_filters_by_level_and_by_phenomenon() -> None:
    data = load(BLUEPRINTS / "warning_appeared.yaml")
    inputs = data["blueprint"]["input"]
    assert set(inputs) == {"warning_event", "min_level", "phenomena", "actions"}
    # It triggers on the event entity -- the appearance of a warning, so the
    # second orange warning of the day runs too.
    assert inputs["warning_event"]["selector"]["entity"]["filter"][0]["domain"] == "event"
    assert [o["value"] for o in inputs["min_level"]["selector"]["select"]["options"]] == [
        "yellow",
        "orange",
        "red",
    ]
    phenomena = inputs["phenomena"]["selector"]["select"]
    assert phenomena["multiple"] is True
    assert {o["value"] for o in phenomena["options"]} == CANONICAL
    # Empty means every phenomenon: the filter must not be a trap that
    # silences the automation by default.
    assert inputs["phenomena"]["default"] == []


def test_the_existing_level_blueprint_is_untouched() -> None:
    # Someone who imported it on 0.3.x must keep exactly what they imported.
    data = load(BLUEPRINTS / "aemet_warning.yaml")
    assert set(data["blueprint"]["input"]) == {"warnings_sensor", "min_level", "actions"}
    assert data["triggers"][0]["attribute"] == "highest_level"


def test_the_voice_assistant_uses_the_real_aemet_codes() -> None:
    # The table had TM/Tm/AV/DU, which AEMET does not issue: heat, cold,
    # avalanche and snowmelt could never be named, only fall back.
    data = load(BLUEPRINTS / "voice_assistant.yaml")
    texts = next(
        step["variables"]["t"] for step in data["actions"]
        if isinstance(step, dict) and "variables" in step and "t" in step["variables"]
    )
    for language, block in texts.items():
        assert set(block["phenomena"]) == CANONICAL, language
