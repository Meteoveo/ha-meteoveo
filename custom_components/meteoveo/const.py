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

# The integration's own version, sent in the User-Agent so the service can tell
# released clients apart. A test keeps it equal to manifest.json.
VERSION: Final = "0.3.3"
USER_AGENT: Final = f"ha-meteoveo/{VERSION}"

# The MeteoVeo account page on the web. An account can be created, and later
# deleted, from inside Home Assistant (email, password and an emailed code --
# no browser needed); this page is only where a station owner manages the
# station itself.
SIGNUP_URL: Final = "https://www.meteoveo.com/#/account"

# Linked from the sign-up form. Accepting them is required to create an
# account; marketing email is a separate, optional choice.
TERMS_URL: Final = "https://www.meteoveo.com/legal/terminos"
PRIVACY_URL: Final = "https://www.meteoveo.com/legal/privacidad"

# Every request is bounded. Home Assistant's shared session would otherwise
# wait for minutes on a stalled connection.
REQUEST_TIMEOUT_S: Final = 30
# Removing the integration must never hang on the network.
REVOKE_TIMEOUT_S: Final = 10

# The API's client kind for this integration (the same key type also serves
# other home-automation clients).
CLIENT_KIND: Final = "home_assistant"

# Languages the service writes in. Anything else falls back to Spanish, the
# product's language.
API_LANGUAGES: Final = ("es", "en", "ca")
DEFAULT_API_LANGUAGE: Final = "es"

# Knowledge-base pages, linked from each config-flow step. They live in this
# repository so the linked text is versioned together with the code it
# describes.
_DOCS_BASE: Final = "https://github.com/meteoveo/ha-meteoveo/blob/main/docs"
DOCS_SETUP_URL: Final = f"{_DOCS_BASE}/setup.md"
DOCS_MEASUREMENTS_URL: Final = f"{_DOCS_BASE}/measurements.md"
DOCS_RECIPROCITY_URL: Final = f"{_DOCS_BASE}/reciprocity.md"
DOCS_TROUBLESHOOTING_URL: Final = f"{_DOCS_BASE}/troubleshooting.md"

CONF_STATION_ID: Final = "station_id"
CONF_STATION_KEY: Final = "station_key"
CONF_MEASUREMENTS: Final = "measurements"
# Whether the mapped pressure entity gives the absolute (station-level) value
# or one already reduced to sea level (MeteoVeo ADR-0844). Stored beside the
# mapping, not inside it: it answers a question about a reading, not about
# which entity feeds it.
CONF_PRESSURE_KIND: Final = "pressure_kind"

# Account-based entries (0.2.0+). The account's session token is used only
# while a flow runs and is never stored; what is stored is a restricted
# integration key that can read the forecast for one place and nothing else.
CONF_INTEGRATION_KEY: Final = "integration_key"
CONF_KEY_ID: Final = "key_id"
CONF_EMAIL: Final = "email"
# The service's numeric id of a station created from Home Assistant. The
# ingest id (CONF_STATION_ID) and key (CONF_STATION_KEY) are what uploads use.
CONF_STATION_REF: Final = "station_ref"

# Bounds the service accepts for the sensor height above ground.
MIN_SENSOR_HEIGHT_CM: Final = 10
MAX_SENSOR_HEIGHT_CM: Final = 5000
DEFAULT_SENSOR_HEIGHT_CM: Final = 200

# The home view (forecast, next hour, warnings) changes at most every few
# minutes; the service asks clients not to poll more often than this.
HOME_UPDATE_INTERVAL_S: Final = 300

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
