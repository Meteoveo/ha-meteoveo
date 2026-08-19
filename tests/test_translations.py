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
    assert {m.key for m in MEASUREMENTS} == set(labels)
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
    # The setup screen substitutes this; a translation that dropped it would
    # leave someone without an account with nowhere to go.
    description = load(language)["config"]["step"]["user"]["description"]
    assert "{signup_url}" in description


# --- Tooltips and knowledge-base links (added with the docs pages) ---------


def data_description_steps(data: dict):
    """Every (step, fields) pair that renders input fields."""
    yield "config.user", data["config"]["step"]["user"]
    yield "config.measurements", data["config"]["step"]["measurements"]
    yield "config.reauth_confirm", data["config"]["step"]["reauth_confirm"]
    yield "options.init", data["options"]["step"]["init"]


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
