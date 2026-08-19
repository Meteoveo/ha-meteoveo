"""Upload interval bounds.

The service treats a station as reporting when a reading arrives within the
grace window. An interval longer than the allowed maximum would let someone
configure a station that quietly falls outside it.
"""

from __future__ import annotations

import pytest

from custom_components.meteoveo.const import (
    DEFAULT_UPLOAD_INTERVAL_S,
    MAX_UPLOAD_INTERVAL_S,
    MIN_UPLOAD_INTERVAL_S,
)
from custom_components.meteoveo.flow_logic import clamp_upload_interval


def test_default_is_one_minute():
    assert DEFAULT_UPLOAD_INTERVAL_S == 60


def test_maximum_is_ten_minutes():
    assert MAX_UPLOAD_INTERVAL_S == 600


@pytest.mark.parametrize("seconds", [60, 120, 300, 600])
def test_values_inside_the_range_are_kept(seconds):
    assert clamp_upload_interval(seconds) == seconds


def test_too_long_is_brought_back_to_the_maximum():
    # Not rejected: a stored value from an older version must still load.
    assert clamp_upload_interval(3600) == MAX_UPLOAD_INTERVAL_S


def test_too_short_is_brought_up_to_the_minimum():
    # Faster than the station itself reports only wastes requests.
    assert clamp_upload_interval(5) == MIN_UPLOAD_INTERVAL_S


@pytest.mark.parametrize("junk", [None, "", "abc", -1, 0])
def test_unusable_values_fall_back_to_the_default(junk):
    assert clamp_upload_interval(junk) == DEFAULT_UPLOAD_INTERVAL_S


def test_the_maximum_leaves_room_inside_the_grace_window():
    # Twelve hours of grace against a ten-minute interval: a single missed
    # upload can never approach the limit on its own.
    grace_seconds = 12 * 3600
    assert MAX_UPLOAD_INTERVAL_S * 12 < grace_seconds
