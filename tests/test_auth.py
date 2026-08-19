"""Credential handling.

Everything here exists so that a mistake stays a mistake instead of becoming
a credential leak.
"""

from __future__ import annotations

import logging

import pytest

from custom_components.meteoveo.auth import (
    Credentials,
    api_headers,
    redact,
    upload_url_and_params,
)
from custom_components.meteoveo.const import UPLOAD_URL


CREDS = Credentials(station_id="MVEXAMPLE1", station_key="s3cret-key-value")


class TestTransport:
    def test_uploads_use_tls(self):
        # Station consoles cannot do TLS, but Home Assistant can. Credentials
        # must never travel in the clear.
        url, _ = upload_url_and_params(CREDS, {"tempf": 70.0}, now_iso="2026-08-20 10:00:00")
        assert url.startswith("https://")
        assert UPLOAD_URL.startswith("https://")

    def test_upload_carries_credentials_and_timestamp(self):
        _, params = upload_url_and_params(CREDS, {"tempf": 70.0}, now_iso="2026-08-20 10:00:00")
        assert params["ID"] == "MVEXAMPLE1"
        assert params["PASSWORD"] == "s3cret-key-value"
        assert params["dateutc"] == "2026-08-20 10:00:00"
        assert params["tempf"] == 70.0

    def test_read_api_uses_authorization_header_not_query(self):
        # A token in a query string ends up in browser history, proxy logs and
        # referrer headers. Reads therefore authenticate with a header.
        headers = api_headers(CREDS)
        assert headers["Authorization"].startswith("Bearer ")
        assert "s3cret-key-value" not in str(headers.get("X-Query", ""))


class TestRedaction:
    """Nothing that identifies or authenticates may reach the log."""

    def test_redact_hides_the_secret(self):
        assert "s3cret-key-value" not in redact(f"key={CREDS.station_key}")

    def test_redact_keeps_the_message_readable(self):
        # A redacted log line still has to be useful for support.
        out = redact(f"upload failed for {CREDS.station_id} key={CREDS.station_key}")
        assert "upload failed" in out
        assert "***" in out

    def test_redact_handles_url_with_credentials(self):
        line = f"{UPLOAD_URL}?ID={CREDS.station_id}&PASSWORD={CREDS.station_key}&tempf=70"
        out = redact(line)
        assert CREDS.station_key not in out
        assert "tempf=70" in out  # the useful part survives

    @pytest.mark.parametrize("text", ["", "nothing secret here"])
    def test_redact_is_safe_on_plain_text(self, text):
        assert redact(text) == text


def test_repr_never_exposes_the_key():
    # Credentials end up inside exception tracebacks and debug dumps; the
    # dataclass repr is the most common accidental path.
    assert "s3cret-key-value" not in repr(CREDS)
    assert "s3cret-key-value" not in str(CREDS)
    # The identifier is not a secret and stays visible for support.
    assert "MVEXAMPLE1" in repr(CREDS)


def test_logging_a_credentials_object_does_not_leak(caplog):
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("test").debug("creds=%s", CREDS)
    assert "s3cret-key-value" not in caplog.text
