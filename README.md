# MeteoVeo — Home Assistant integration

Send your weather station's readings to [MeteoVeo](https://www.meteoveo.com)
from Home Assistant, and bring what MeteoVeo knows about your station back
into your automations.

> **Status: early development.** Submitted to the HACS default list.

The integration ships its own brand icons in `custom_components/meteoveo/brand/`.
Since Home Assistant 2026.3.0 that is the supported route for custom
integrations — the `home-assistant/brands` repository no longer accepts them.

## Documentation

- [Setup guide](docs/setup.md) — account, station, adding the integration
- [Measurements](docs/measurements.md) — what each field expects, units, pitfalls
- [Reciprocity](docs/reciprocity.md) — the give-data-get-data rules
- [Troubleshooting](docs/troubleshooting.md) — errors and what they mean

## Why this exists

Most consumer weather-station gateways — the Fine Offset family, sold as
Ecowitt, Ambient Weather, Froggit, Sainlogic, GARNI and others — have exactly
**one** "customized upload" slot. If Home Assistant already occupies it, there
is no room for a second service. This integration removes the conflict: the
device keeps talking to Home Assistant, and Home Assistant forwards to
MeteoVeo.

It also covers hardware that cannot upload to a custom server at all (Davis,
Netatmo, La Crosse, AcuRite). If Home Assistant can see the reading, it can be
forwarded.

## What you get

**Sent to MeteoVeo.** You choose which entity feeds each measurement:

| Measurement | Units accepted |
|---|---|
| Temperature | °C, °F |
| Humidity | % |
| Pressure (station level, not sea level) | hPa, mbar, inHg |
| Wind speed | m/s, km/h, mph |
| Wind gust | m/s, km/h, mph |
| Wind direction | degrees |
| Daily rainfall (accumulated since midnight) | mm, in |
| Solar radiation | W/m² |

Conversion is automatic. A reading that is `unknown`, `unavailable` or
physically impossible is **left out** rather than sent as zero — a gap must
never be indistinguishable from a measurement.

**Brought back from MeteoVeo:**

- **Best forecast model** for your location, with its error and bias. Until
  there is enough history the sensor says `collecting` and counts down the
  days — the number comes from your own station's data.
- **Sensor problem** — on when the service has flagged something about your
  station, with the individual findings as an attribute.
- **Accepted uploads** and **Last upload**, so a silent failure is visible.
- **Forecast access remaining** — see below.

## An exchange, not a feed

Forecast and nowcast are available to stations that report. If nothing
arrives from your station for **12 hours**, those pause; your station's own
data — sensor findings, upload state — stays available throughout, so you can
see what went wrong. The first reading that arrives restores access
immediately, with no waiting period.

You are emailed after 1, 6 and 12 hours of silence, and the **Forecast access
remaining** sensor counts down the margin, so an automation can warn you
before it runs out:

```yaml
automation:
  - alias: Warn before MeteoVeo access pauses
    trigger:
      - platform: numeric_state
        entity_id: sensor.<your_station>_forecast_access_remaining
        below: 3
    action:
      - action: notify.persistent_notification
        data:
          message: "The station has not reported for a while."
```

## Requirements

- A MeteoVeo account with at least one station
- The station's ingest ID and key

## Installation

### HACS

Until the default-list submission is merged, add it as a custom repository:

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/meteoveo/ha-meteoveo`, category **Integration**
3. Install **MeteoVeo**, then restart Home Assistant

### Manually

1. Copy `custom_components/meteoveo` into your Home Assistant
   `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. **Settings → Devices & Services → Add Integration → MeteoVeo**
2. Enter the **station ID** and **station key**.
   - No station yet? Create an account at
     [meteoveo.com](https://www.meteoveo.com/#/account) first. Sign-up needs a
     browser: an email address, a password, and a confirmation code sent to
     that address. A passkey can be added later and is optional.
   - Lost the key? Open the station's settings page on meteoveo.com and
     generate a new one. **Generating a new key immediately invalidates the
     old one**, so anything already using it will stop.
3. **Map your entities.** Leave a measurement empty if your station does not
   report it — every field is optional. One entity per measurement.

The credentials are checked while you are still on the screen: if they are
wrong, you find out immediately rather than after hours of silence.

### Configuration parameters

| Parameter | Required | Meaning |
|---|---|---|
| Station ID | yes | Identifies the station. Shown when the station is created. |
| Station key | yes | Authenticates uploads and reads. Secret. |
| Measurement mapping | no | Which entity feeds which measurement. Change any time via **Configure**. |

Pressure must be **station-level (absolute)** pressure. MeteoVeo reduces it to
sea level using the station's elevation; sending an already-reduced value
would apply the correction twice.

Daily rainfall must be **accumulated since local midnight**, not a per-interval
total. If your station integration only exposes an interval value, a Home
Assistant [utility meter](https://www.home-assistant.io/integrations/utility_meter/)
on a daily cycle produces the right figure.

## Changing the mapping

**Settings → Devices & Services → MeteoVeo → Configure.** Clearing every
measurement is allowed; the integration simply stops uploading.

## If the key changes

Home Assistant will ask you to re-enter it (a repair notification appears).
The station keeps its identity, so history and entity IDs are preserved.

## Removal

**Settings → Devices & Services → MeteoVeo → ⋮ → Delete.** This removes the
entities and stops uploads. Readings already sent to MeteoVeo stay there; to
remove those, delete the station from your account on meteoveo.com.

If you installed manually, also delete `config/custom_components/meteoveo`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| *"The station ID or key was not accepted"* | Wrong credentials, or a new key was generated and invalidated this one. |
| *"Could not reach MeteoVeo"* | The service could not be contacted. Your credentials were not tested; nothing needs changing. |
| Uploads accepted stays at 0 | No measurement is mapped, or every mapped entity is unavailable. |
| A measurement never arrives | Its entity reports a unit this integration does not recognise. Unknown units are skipped rather than guessed. |

Debug logging:

```yaml
logger:
  logs:
    custom_components.meteoveo: debug
```

The station key is excluded from log output.

## Privacy and security

See [SECURITY.md](SECURITY.md). In short: all requests use TLS, the key is
kept out of logs and `repr()`, and a station credential is limited to that one
station — it cannot sign in or reach any other station.

## Development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python scripts/audit.py   # pre-publication check
.venv/bin/python -m pytest -q
```

## License

MIT
