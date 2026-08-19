# Measurements

The integration uploads up to eight measurements. Each one is fed by **one**
Home Assistant entity of your choice; a measurement left empty is treated as
"my station does not have this sensor" and is simply not uploaded.

Home Assistant already knows the unit of each entity, and the integration
converts to what the service expects — you do not need to change your
station's units.

| Measurement | What to pick | Accepted units |
| --- | --- | --- |
| Temperature | The **outdoor** temperature sensor | °C, °F |
| Humidity | Outdoor relative humidity | % |
| Pressure | **Station-level (absolute)** pressure. The service reduces it to sea level using the station's elevation — an already reduced value would be corrected twice | hPa, mbar, inHg |
| Wind speed | Sustained wind speed (the averaged value, not the gust) | m/s, km/h, mph |
| Wind gust | Peak gust | m/s, km/h, mph |
| Wind direction | Direction in degrees, 0–360, meteorological convention (the direction the wind comes **from**) | ° |
| Daily rainfall | Rain accumulated **since midnight** — not the rain rate, and not the total-since-installation counter | mm, in |
| Solar radiation | Global solar irradiance | W/m² |

## Common pitfalls

- **Indoor sensors.** Many consoles expose both indoor and outdoor
  temperature/humidity. Pick the outdoor one; the entity picker cannot tell
  them apart for you.
- **Rain rate vs. daily rain.** The service expects the daily accumulation.
  A rate (mm/h) uploaded as daily rain produces obviously wrong values and
  will be flagged by the sensor-health check.
- **Relative vs. absolute pressure.** Many consoles expose both. Pick the
  **absolute** (station-level) one: the service does the sea-level reduction
  itself, so an already reduced value gets corrected twice and sits
  systematically above every neighbouring station.
- **Unrecognised units.** An entity whose unit is not in the table above is
  skipped rather than guessed — a value uploaded in a wrong unit would be
  worse than a gap.
- **Two entities for the same measurement.** Not possible by design — one
  entity per measurement keeps the upload unambiguous.

## Changing the mapping later

Open **Settings → Devices & services → MeteoVeo → Configure**. The same
screen appears; previously chosen entities are pre-filled as suggestions and
can be cleared to mark a measurement as unavailable again.
