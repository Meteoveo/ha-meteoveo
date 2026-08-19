"""Setup logic, kept separate from the Home Assistant flow class.

What a setup screen does with a failure decides whether people can recover.
A typo in the key and a service outage must not produce the same message: one
is fixed by retyping, the other by waiting.
"""

from __future__ import annotations

import pytest

from custom_components.meteoveo.auth import Credentials
from custom_components.meteoveo.client import InvalidCredentials, ServiceUnavailable
from custom_components.meteoveo.flow_logic import (
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_UNKNOWN,
    clean_station_id,
    entry_title,
    error_for,
    unique_id_for,
)


class TestStationIdCleanup:
    """People paste from the web page, so leading spaces and case vary."""

    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("MVEXAMPLE1", "MVEXAMPLE1"),
            ("  MVEXAMPLE1  ", "MVEXAMPLE1"),
            ("mvexample1", "MVEXAMPLE1"),
            ("\tMVEXAMPLE1\n", "MVEXAMPLE1"),
        ],
    )
    def test_whitespace_and_case_are_forgiven(self, typed, expected):
        assert clean_station_id(typed) == expected

    def test_empty_input_stays_empty(self):
        # The flow decides what to do about it; cleanup does not invent a value.
        assert clean_station_id("   ") == ""


class TestErrorMapping:
    """The three outcomes a user can act on."""

    def test_rejected_key_asks_the_user_to_check_it(self):
        assert error_for(InvalidCredentials("nope")) == ERROR_INVALID_AUTH

    def test_outage_asks_the_user_to_wait(self):
        # Not "invalid auth": telling someone their key is wrong when the
        # service is down sends them to regenerate a perfectly good key --
        # which would break the station that is already using it.
        assert error_for(ServiceUnavailable("503")) == ERROR_CANNOT_CONNECT

    @pytest.mark.parametrize("failure", [TimeoutError(), OSError("dns"), ValueError("odd")])
    def test_anything_else_is_reported_as_unknown(self, failure):
        # An unexpected failure must not masquerade as a credential problem.
        assert error_for(failure) == ERROR_UNKNOWN


class TestIdentity:
    def test_unique_id_is_the_station_id(self):
        # Adding the same station twice has to be caught; the station id is
        # what stays stable across key rotations.
        assert unique_id_for("MVEXAMPLE1") == "mvexample1"

    def test_unique_id_survives_a_key_rotation(self):
        first = unique_id_for(clean_station_id(" mvexample1 "))
        second = unique_id_for(clean_station_id("MVEXAMPLE1"))
        assert first == second

    def test_entry_title_prefers_the_station_name(self):
        assert entry_title({"station": {"name": "Garden"}}, "MVEXAMPLE1") == "Garden"

    @pytest.mark.parametrize("view", [{}, {"station": {}}, {"station": {"name": ""}}, None])
    def test_entry_title_falls_back_to_the_station_id(self, view):
        # A nameless entry would be unidentifiable in the device list.
        assert entry_title(view, "MVEXAMPLE1") == "MVEXAMPLE1"


def test_credentials_are_built_from_cleaned_input():
    creds = Credentials(station_id=clean_station_id(" mvexample1 "), station_key="  key  ".strip())
    assert creds.station_id == "MVEXAMPLE1"
    assert creds.station_key == "key"
