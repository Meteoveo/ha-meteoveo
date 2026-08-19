# MeteoVeo — Home Assistant integration

Send your weather station's readings to [MeteoVeo](https://www.meteoveo.com)
from Home Assistant, and bring MeteoVeo's forecast and nowcast back into your
automations.

> **Status: early development.** Not yet published to HACS.

## Why this exists

Most consumer gateways (the Fine Offset family — Ecowitt, Froggit, Ambient
Weather, Sainlogic, GARNI…) have exactly **one** "customized upload" slot. If
Home Assistant already occupies it, there is no room left for a second
service. This integration removes the conflict: **the device keeps talking to
Home Assistant, and Home Assistant forwards to MeteoVeo.**

It also works for hardware that cannot upload to a custom server at all
(Davis, Netatmo, La Crosse, AcuRite…) — if Home Assistant can see it, it can
be forwarded.

## What it does

**Push — your readings to MeteoVeo**

You pick which Home Assistant entity feeds each measurement. One entity per
measurement per station:

| Measurement | Sent as |
|---|---|
| Temperature | `tempf` |
| Humidity | `humidity` |
| Pressure (station level) | `absbaromin` |
| Wind speed | `windspeedmph` |
| Wind gust | `windgustmph` |
| Wind direction | `winddir` |
| Daily rainfall (cumulative) | `dailyrainin` |
| Solar radiation | `solarradiation` |

Unit conversion is automatic. Values that are `unknown`, `unavailable` or
outside physical plausibility are **left out** rather than sent as zero — a
missing reading must never look like a measurement.

**Pull — MeteoVeo back into Home Assistant** *(in progress)*

- Forecast for your station's exact location, with calibrated precipitation
  probability
- Storm nowcast and lightning activity nearby
- Your station's health: deviation from neighbours, last upload error
- Which forecast model performs best at your location — or how many days of
  data are still needed before we can tell

## Requirements

- A MeteoVeo account and a station (the integration links to sign-up if you
  don't have one yet)
- The station's ingest ID and key, shown when the station is created

## Language support

English, Spanish, Catalan and Hungarian.

## License

MIT
