"""Translation completeness.

A missing key does not crash Home Assistant -- it silently shows the raw key
instead of a sentence, which looks like a bug in someone else's language and
is easy to ship without noticing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.meteoveo.wu_payload import MEASUREMENTS

TRANSLATIONS = Path(__file__).resolve().parents[1] / "custom_components/meteoveo/translations"
LANGUAGES = ["en", "es", "ca", "hu"]


def load(language: str) -> dict:
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, value


@pytest.mark.parametrize("language", LANGUAGES)
def test_language_file_exists_and_parses(language):
    assert load(language)


def test_every_language_has_exactly_the_same_keys():
    # English is the reference; a language with extra or missing keys is a
    # translation that drifted.
    reference = {key for key, _ in flatten(load("en"))}
    for language in LANGUAGES[1:]:
        assert {key for key, _ in flatten(load(language))} == reference, language


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_measurement_has_a_label(language):
    data = load(language)
    labels = data["config"]["step"]["measurements"]["data"]
    # One field in the form is not a measurement: how the barometer reports
    # (MeteoVeo ADR-0844). Named explicitly, so a measurement added without a
    # label is still caught.
    assert set(labels) == {m.key for m in MEASUREMENTS} | {"pressure_kind"}
    for key, text in labels.items():
        assert text.strip(), f"{language}: {key} has no label"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_value_was_left_untranslated(language):
    # A value identical to English in every language would mean the file was
    # copied and never translated. Checked on the error messages, which are
    # the longest prose and would be the most obvious to a reader.
    if language == "en":
        return
    english = dict(flatten(load("en")))
    translated = dict(flatten(load(language)))
    errors = [k for k in english if k.startswith("config.error.")]
    assert any(translated[k] != english[k] for k in errors), language


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_signup_placeholder_survives_translation(language):
    # The station-key screen substitutes this; a translation that dropped it
    # would leave a station owner without the page where the key is shown.
    description = load(language)["config"]["step"]["station_key"]["description"]
    assert "{signup_url}" in description


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_legal_links_survive_translation(language):
    # Accepting the terms is only meaningful if they can be read from the form.
    description = load(language)["config"]["step"]["create_account"]["description"]
    assert "{terms_url}" in description
    assert "{privacy_url}" in description


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_code_screen_names_the_address(language):
    assert "{email}" in load(language)["config"]["step"]["verify_code"]["description"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_menu_option_has_a_label(language):
    data = load(language)
    assert set(data["config"]["step"]["user"]["menu_options"]) == {
        "create_account",
        "login",
        "station_key",
    }
    assert set(data["options"]["step"]["init"]["menu_options"]) == {
        "location",
        "measurements",
        # ADR-0866 D9: the station door, reachable after setup as well.
        "add_station",
        # MeteoVeo ADR-0872: the public-visibility switch for the station.
        "visibility",
        "delete_account",
    }


# --- Tooltips and knowledge-base links (added with the docs pages) ---------


def data_description_steps(data: dict):
    """Every (step, fields) pair that renders input fields."""
    for flow in ("config", "options"):
        for name, step in data[flow]["step"].items():
            if "data" in step:
                yield f"{flow}.{name}", step


def test_every_form_step_is_checked():
    # Guards the generic walk above: a step that renders fields must be found.
    names = {name for name, _ in data_description_steps(load("en"))}
    assert {"config.station_key", "config.create_account", "config.login",
            "config.location", "options.delete_account"} <= names


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_field_has_a_tooltip(language):
    # data_description renders as helper text under the field -- the tooltip
    # the UI asks for. A field without one is a bare label, which is exactly
    # what the guideline (and the user) complained about.
    data = load(language)
    for step_name, step in data_description_steps(data):
        fields = step["data"]
        tooltips = step.get("data_description", {})
        assert set(tooltips) == set(fields), f"{language}: {step_name}"
        for key, text in tooltips.items():
            assert text.strip(), f"{language}: {step_name}.{key} tooltip empty"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_docs_link_survives_translation(language):
    # Each step's description links to the relevant knowledge-base page; a
    # translation that drops the placeholder loses the "?" for that language.
    data = load(language)
    for step_name, step in data_description_steps(data):
        assert "{docs_url}" in step["description"], f"{language}: {step_name}"


def test_strings_json_is_the_english_translation():
    # hassfest validates strings.json, Home Assistant renders en.json. If the
    # two drift, what was reviewed is not what English users see.
    strings = json.loads(
        (TRANSLATIONS.parent / "strings.json").read_text(encoding="utf-8")
    )
    assert strings == load("en")


def test_icons_match_translation_keys() -> None:
    """Every icon belongs to an entity the integration translates (and so creates)."""
    import json
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / "meteoveo"
    icons = json.loads((base / "icons.json").read_text(encoding="utf-8"))["entity"]
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))["entity"]
    for platform, keys in icons.items():
        for key, icon in keys.items():
            assert key in strings.get(platform, {}), f"{platform}.{key} has an icon but no translation"
            assert icon["default"].startswith("mdi:")


# --- ADR-0866: the Plus surface -------------------------------------------
#
# The reciprocity offer is only worth anything if it is stated where the
# choice is made. Until 0.3.0 the word "Plus" appeared in no language file at
# all, while the service was already granting the level.

#: Entities that only exist on an account with the Plus level, and the one
#: that reports the level itself.
PLUS_ENTITY_KEYS = {
    "sensor": ("account_level", "nearest_lightning"),
    "binary_sensor": ("lightning_nearby",),
    "camera": ("radar_playback",),
    "select": ("radar_window", "radar_extent"),
}

RADAR_WINDOW_OPTIONS = {"1h", "3h", "6h", "12h", "24h"}
RADAR_EXTENT_OPTIONS = {"local", "region", "spain"}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_station_question_says_what_a_station_unlocks(language):
    # ADR-0866 D1. Both screens of the station door name the level, and say
    # that it counts outside Home Assistant as well -- that is the whole
    # offer, and leaving it out is what made the conversion zero.
    steps = load(language)["config"]["step"]
    for name in ("has_station", "station_details"):
        assert "Plus" in steps[name]["description"], f"{language}: {name}"
    # The promise is conditional on the cadence, so the cadence is named.
    assert "10" in steps["has_station"]["description"], language


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_options_door_repeats_the_very_same_offer(language):
    # ADR-0866 D9: the Options entry is the same door, so it says the same
    # thing -- a second wording would be a second promise to keep in step.
    data = load(language)
    assert (
        data["options"]["step"]["add_station"]["description"]
        == data["config"]["step"]["has_station"]["description"]
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_plus_entities_are_named_and_their_states_translated(language):
    entity = load(language)["entity"]
    for platform, keys in PLUS_ENTITY_KEYS.items():
        for key in keys:
            assert entity[platform][key]["name"].strip(), f"{language}: {platform}.{key}"
    assert set(entity["sensor"]["account_level"]["state"]) == {"free", "plus"}
    assert set(entity["select"]["radar_window"]["state"]) == RADAR_WINDOW_OPTIONS
    assert set(entity["select"]["radar_extent"]["state"]) == RADAR_EXTENT_OPTIONS


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_entity_or_device_name_contains_plus(language):
    # ADR-0866 D10.6: the level changes, the name would not follow -- and a
    # name that advertises reads as advertising.
    entity = load(language)["entity"]
    for platform, keys in PLUS_ENTITY_KEYS.items():
        for key in keys:
            if key == "account_level":
                continue  # its *state* is "Plus"; its name is not
            assert "Plus" not in entity[platform][key]["name"], f"{language}: {key}"


def test_the_user_interface_lists_no_plus_features_and_sells_nothing():
    # ADR-0866 D2 and D10.3/D10.4: the feature list is the server's, and
    # lives in the README. An integration is not a shop window.
    text = (TRANSLATIONS.parent / "strings.json").read_text(encoding="utf-8").lower()
    for forbidden in ("upgrade", "fire alert", "saved places", "buy ", "store.meteoveo"):
        assert forbidden not in text, forbidden


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_widest_radar_area_does_not_promise_the_canaries(language):
    # The key is "spain", but the picture is the peninsula and the Balearics:
    # our radar field measures nothing at all over the Canaries, so a label
    # saying "Spain" would promise an empty map.
    label = load(language)["entity"]["select"]["radar_extent"]["state"]["spain"]
    for promise in ("Canar", "Canàr", "Kanári"):
        assert promise not in label, language


@pytest.mark.parametrize("language", LANGUAGES)
def test_both_pressure_kinds_are_named(language):
    # The dropdown shows these two labels. An untranslated option would read
    # as "sea_level", which says nothing to the person choosing.
    options = load(language)["selector"]["pressure_kind"]["options"]
    assert set(options) == {"absolute", "sea_level"}
    for key, text in options.items():
        assert text.strip(), f"{language}: {key} has no label"
