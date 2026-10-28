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
| Pressure | Your station's pressure, plus one answer: is it the **absolute** (station-level) value or the **relative** one (already reduced to sea level)? | hPa, mbar, inHg |
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
- **Relative vs. absolute pressure.** Many consoles expose both, and they
  differ by about 0.12 hPa for every metre of altitude. Either one can be
  uploaded — but the **Pressure type** field right under the picker has to
  match what you chose. MeteoVeo performs the sea-level reduction itself, so
  a mismatched answer shifts the pressure by that much, systematically and
  always in the same direction.
- **Unrecognised units.** An entity whose unit is not in the table above is
  skipped rather than guessed — a value uploaded in a wrong unit would be
  worse than a gap.
- **Two entities for the same measurement.** Not possible by design — one
  entity per measurement keeps the upload unambiguous.

## Absolute or relative? How to tell

Consoles are rarely explicit about which one they publish, and the difference
is not small: about 0.12 hPa per metre of altitude, so 6 hPa at 50 m — that is
a different weather situation, not a rounding error.

Two ways to find out, no instruments needed:

1. **Compare with a station at the coast.** Pick a station whose altitude is
   near zero and compare its pressure with yours at the same minute. If the
   two agree within a hPa or so, yours is **relative**: that is the whole
   point of the reduction, that sea-level values match across long distances.
2. **Do the arithmetic.** Take that coastal reading and subtract roughly
   0.12 hPa for every metre of your own altitude. If your station's number
   lands near the result, it is **absolute**.

Where a console exposes both, they are usually labelled "absolute" or
"station" and "relative" or "sea level". Where it publishes only one, it is
more often the relative value — which is why the question is asked rather
than assumed.

## Changing the mapping later

Open **Settings → Devices & services → MeteoVeo → Configure**. The same
screen appears; previously chosen entities are pre-filled as suggestions and
can be cleared to mark a measurement as unavailable again.
