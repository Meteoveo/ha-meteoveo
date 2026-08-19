"""Constants for the MeteoVeo integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "meteoveo"

# Uploads always go over TLS.
#
# MeteoVeo also accepts uploads over plain HTTP on a separate hostname, because
# most consumer weather-station consoles cannot speak TLS at all -- they only
# offer a "server" and a "port" field. Home Assistant has no such limitation,
# so this integration always uses HTTPS: the station credentials must never
# travel in the clear.
UPLOAD_URL: Final = "https://www.meteoveo.com/weatherstation/updateweatherstation.php"

# Read-only API for forecast, nowcast and station health.
API_BASE: Final = "https://www.meteoveo.com/api"

# Where to send someone who does not have a station yet. Account creation uses
# passkeys, which need a real browser -- it cannot happen inside Home Assistant.
SIGNUP_URL: Final = "https://www.meteoveo.com/#/cuenta"

CONF_STATION_ID: Final = "station_id"
CONF_STATION_KEY: Final = "station_key"
CONF_MEASUREMENTS: Final = "measurements"

# One upload per minute. Weather stations report at this rate at best, and the
# server rejects bursts, so there is nothing to gain from going faster.
DEFAULT_UPLOAD_INTERVAL_S: Final = 60

# How long the server needs to observe a station before it can say which
# forecast model performs best there. Until then the integration reports how
# many days are still missing.
MIN_SKILL_SAMPLES: Final = 10
