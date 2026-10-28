"""Mapping measurements to entities.

Not every station reports every measurement. A user with no solar sensor must
be able to say so and move on -- an integration that demands a value for
everything is an integration that cannot be set up.
"""

from __future__ import annotations

import pytest

from custom_components.meteoveo.const import CONF_PRESSURE_KIND
from custom_components.meteoveo.selection import (
    NOT_AVAILABLE,
    selected_entity_ids,
    split_pressure_kind,
    validate_selection,
)
from custom_components.meteoveo.wu_payload import (
    MEASUREMENTS,
    PRESSURE_ABSOLUTE,
    PRESSURE_SEA_LEVEL,
)


def test_every_measurement_may_be_left_unmapped():
    # Selecting nothing at all is valid input; it just has nothing to upload.
    selection = {m.key: NOT_AVAILABLE for m in MEASUREMENTS}
    assert validate_selection(selection) == {}


def test_unmapped_measurements_are_dropped_not_stored_as_placeholders():
    selection = {"temperature": "sensor.outside_temp", "solar_radiation": NOT_AVAILABLE}
    assert validate_selection(selection) == {"temperature": "sensor.outside_temp"}


@pytest.mark.parametrize("empty", [NOT_AVAILABLE, "", None])
def test_all_the_ways_of_saying_not_available(empty):
    assert validate_selection({"temperature": empty}) == {}


def test_unknown_measurement_key_is_rejected():
    with pytest.raises(ValueError, match="unknown measurement"):
        validate_selection({"no_such_measurement": "sensor.x"})


def test_one_entity_per_measurement():
    # The upload protocol carries a single field per measurement; two sources
    # in one series would make the data meaningless.
    with pytest.raises(ValueError, match="one entity"):
        validate_selection({"temperature": ["sensor.a", "sensor.b"]})


def test_the_same_entity_may_feed_two_measurements():
    # Unusual but legitimate: some integrations expose speed and gust from a
    # single entity with attributes.
    selection = {"wind_speed": "sensor.wind", "wind_gust": "sensor.wind"}
    assert validate_selection(selection) == selection


def test_selected_entity_ids_lists_what_to_watch():
    # The coordinator subscribes to exactly these entities, and to nothing it
    # was not given.
    selection = {"temperature": "sensor.t", "humidity": NOT_AVAILABLE, "pressure": "sensor.p"}
    assert selected_entity_ids(selection) == ["sensor.p", "sensor.t"]


def test_nothing_selected_means_nothing_to_watch():
    assert selected_entity_ids({m.key: NOT_AVAILABLE for m in MEASUREMENTS}) == []


# The measurements form asks one question that is not an entity: how the
# barometer reports (MeteoVeo ADR-0844). It is kept out of the mapping, so
# the stored selection only ever holds measurement keys.


def test_the_pressure_kind_is_separated_from_the_entity_mapping():
    answers = {"temperature": "sensor.t", CONF_PRESSURE_KIND: PRESSURE_SEA_LEVEL}
    mapping, kind = split_pressure_kind(answers)
    assert mapping == {"temperature": "sensor.t"}
    assert kind == PRESSURE_SEA_LEVEL
    # What is left must pass the mapping validation, which refuses anything
    # that is not a measurement.
    assert validate_selection(mapping) == {"temperature": "sensor.t"}


def test_an_unanswered_pressure_kind_means_absolute():
    assert split_pressure_kind({"humidity": "sensor.h"}) == (
        {"humidity": "sensor.h"},
        PRESSURE_ABSOLUTE,
    )


def test_an_unknown_pressure_kind_is_refused():
    # Guessing here would silently decide which way a reading is corrected.
    with pytest.raises(ValueError):
        split_pressure_kind({CONF_PRESSURE_KIND: "qnh"})
