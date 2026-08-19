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

# One upload per minute -- the rate consumer stations report at, and the rate
# the service expects.
DEFAULT_UPLOAD_INTERVAL_S: Final = 60

# Ten minutes is as sparse as a station may report. The service treats a
# station as active when a reading arrives inside its grace window; a longer
# interval would let someone configure a station that quietly falls outside
# it during ordinary operation.
MAX_UPLOAD_INTERVAL_S: Final = 600

# Faster than the station itself measures only wastes requests.
MIN_UPLOAD_INTERVAL_S: Final = 60

# How long the server needs to observe a station before it can say which
# forecast model performs best there. Until then the integration reports how
# many days are still missing.
MIN_SKILL_SAMPLES: Final = 10
