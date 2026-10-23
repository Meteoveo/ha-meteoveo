# The MeteoVeo card

The integration ships its own Lovelace card. There is nothing extra to
install: when the integration loads, it serves `meteoveo-card.js` and
registers it as a frontend resource, and the card appears in the
**Add card** dialog as **MeteoVeo**.

## What it shows

From top to bottom:

1. **Now** — the town, the current temperature, the condition and a short
   line with humidity and wind. The place is the town of your config entry;
   no weather-station name is ever shown. Under it a detail row: feels-like
   temperature, the UV index with a dot in the WHO colour (green 0–2, yellow
   3–5, orange 6–7, red 8–10, violet 11+) and today's maximum when it is
   higher, sunrise and sunset (from Home Assistant's own `sun.sun`), and the
   dew point. Each item appears only when its source exists — the weather
   entity's attributes first, the integration's sensors as the fallback — so
   an installation without the 0.2.0 sensors shows the row as far as it can.
2. **Next 3 hours** — MeteoVeo's own nowcast in 10-minute steps: a bar per
   step, higher and darker the heavier the rain, a dashed rail where it stays
   dry, and a striped bar where the step is uncertain. One sentence says what
   it means (*Lluvia moderada en ~20 min*, *Lluvia débil hasta las 14:30*,
   *Sin lluvia en las próximas 3 h*) and the small *radar · hace 2 min* tells
   how old the radar run is — it turns amber past 45 minutes and the block
   says *Sin datos recientes del radar* past two hours. Outside the nowcast
   coverage the block is simply not drawn.
3. **AEMET warnings** — one banner per warning, coloured yellow, orange or
   red, with the phenomenon, the headline and its validity: an active warning
   says until when (*hasta las 21:00*, *hasta mañana a las 01:00*), an
   upcoming one — drawn with a dashed edge — from when (*desde mañana a las
   06:00*). Active warnings come first, highest level first; expired ones are
   not shown. Beyond two, a *+N más* link unfolds the rest.
4. **Hourly** — a horizontally scrollable strip: hour, condition, temperature
   and the rain probability when it is at least 10 %. When any visible hour
   has rain in the forecast, each hour also gets its amount in mm and a small
   bar in the same blues as the 3-hour strip (light under 1 mm, mid 1–5 mm,
   deep from 5 mm); a dry window shows no bars at all.
5. **Daily** — one row per day with the condition, rain probability, and the
   min–max temperature as a bar on the week's scale.

The card follows the Home Assistant theme (light and dark) and uses
MeteoVeo's accent colours for rain, warnings and the temperature bars.
Texts are in Spanish, English or Catalan (and Hungarian), chosen from your
Home Assistant language (English otherwise); times use your time zone and
12/24-hour setting.

**Compact mode** (`compact: true`) keeps the "now" header and the
next-3-hours strip — for a small dashboard or a narrow column of a sections
view. Which warnings it still shows is up to you (`compact_warnings`):
`severe` (default — an active orange or red warning), `all` (every active
warning) or `none`.

## Adding the card

**Visual editor.** Add card → MeteoVeo. The weather entity of your first
MeteoVeo config entry is pre-selected; the "rain soon" and warnings sensors of
the same entry are found automatically.

**YAML.** Only `entity` is required:

```yaml
type: custom:meteoveo-card
entity: weather.meteoveo_castellonet_de_la_conquesta
```

All options:

```yaml
type: custom:meteoveo-card
entity: weather.meteoveo_castellonet_de_la_conquesta   # required, a MeteoVeo weather entity
rain_entity: binary_sensor.meteoveo_castellonet_de_la_conquesta_rain_in_the_next_hour   # optional override
warnings_entity: sensor.meteoveo_castellonet_de_la_conquesta_weather_warnings       # optional override
show_next_hour: true     # the 3-hour rain strip
show_warnings: true      # the AEMET banners
show_hourly: true
show_daily: true
show_details: true       # feels like, UV, sunrise/sunset, dew point
show_precipitation: true # mm bars in the hourly strip
compact: false           # header + next 3 hours only
hourly_count: 12         # 3–48 hours in the strip
daily_count: 7           # 1–14 days in the list
```

| Option | Default | Meaning |
|---|---|---|
| `entity` | — | The `weather.*` entity of a MeteoVeo config entry. |
| `rain_entity` | found by device | The entry's `binary_sensor` "rain soon" sensor, if you want to point at a different one. |
| `warnings_entity` | found by device | The entry's warnings `sensor`. |
| `show_next_hour` | `true` | Show the next-3-hours rain strip. |
| `show_warnings` | `true` | Show the AEMET warning banners when a warning is active or upcoming. |
| `show_hourly` | `true` | Show the hourly strip. |
| `show_daily` | `true` | Show the daily list. |
| `show_details` | `true` | Show the detail row under the header (feels like, UV, sun, dew point). |
| `show_precipitation` | `true` | Show the mm bars in the hourly strip when the window has rain. |
| `show_radar` | `true` | The radar loop — the last hour of radar and the next hour's nowcast around your place (the integration's `image` entity). Not shown in compact mode. |
| `compact` | `false` | Header and the next-3-hours strip only. |
| `compact_warnings` | `severe` | In compact mode: `severe` = active orange and red warnings, `all` = every active warning, `none` = no warnings. |
| `hourly_count` | `12` | Hours in the strip. |
| `daily_count` | `7` | Days in the list (the free level provides 7). |

In a **sections** view the card takes the full width by default and can be
narrowed to half.

## Where the data comes from

The card reads only the integration's entities: the weather entity (current
conditions, and the hourly and daily forecasts over the `weather/subscribe_forecast`
websocket subscription), the "rain soon" binary sensor (the 10-minute steps and
their age), the warnings sensor, and — when they exist — the feels-like, dew
point, UV index and UV maximum sensors of the same device; sunrise and sunset
come from Home Assistant's `sun.sun`. It makes no network requests of its own,
and it loads no code from the internet — it works on an offline Home Assistant.

## Troubleshooting

- **"Añade la integración MeteoVeo y elige su entidad «weather»."** — the
  `entity` in the card's YAML does not exist. Pick it again in the editor.
- **"Sin datos de MeteoVeo ahora mismo"** — the weather entity is
  `unavailable`; see [troubleshooting](troubleshooting.md).
- **No "Next 3 hours" block** — the place is outside the radar nowcast coverage
  (the binary sensor is `unavailable`), or `show_next_hour` is off.
- **Card not in the picker after an update** — reload the browser page
  (the file is cached by the browser, not by Home Assistant).

## Developing the card

The card is one plain ES module, `custom_components/meteoveo/frontend/meteoveo-card.js`,
with no build step. `tools/card-preview/index.html` renders it with a mocked
`hass` in several states (open it in a browser from a local web server, or
with Chrome's `--allow-file-access-from-files`; `?theme=dark`, `?lang=en`).
The pure helpers (steps → sentence) are tested with
`node --test tools/card-preview/card.test.mjs`.
