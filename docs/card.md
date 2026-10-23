# The MeteoVeo card

The integration ships its own Lovelace card. There is nothing extra to
install: when the integration loads, it serves `meteoveo-card.js` and
registers it as a frontend resource, and the card appears in the
**Add card** dialog as **MeteoVeo**.

## What it shows

From top to bottom:

1. **Now** — the town, the current temperature, the condition and a short
   line with humidity and wind. The place is the town of your config entry;
   no weather-station name is ever shown.
2. **Next 3 hours** — MeteoVeo's own nowcast in 10-minute steps: a bar per
   step, higher and darker the heavier the rain, a dashed rail where it stays
   dry, and a striped bar where the step is uncertain. One sentence says what
   it means (*Lluvia moderada en ~20 min*, *Lluvia débil hasta las 14:30*,
   *Sin lluvia en las próximas 3 h*) and the small *radar · hace 2 min* tells
   how old the radar run is — it turns amber past 45 minutes and the block
   says *Sin datos recientes del radar* past two hours. Outside the nowcast
   coverage the block is simply not drawn.
3. **AEMET warnings** — a banner coloured yellow, orange or red with the
   highest active warning; only when there is one.
4. **Hourly** — a horizontally scrollable strip: hour, condition, temperature
   and the rain probability when it is at least 10 %.
5. **Daily** — one row per day with the condition, rain probability, and the
   min–max temperature as a bar on the week's scale.

The card follows the Home Assistant theme (light and dark) and uses
MeteoVeo's accent colours for rain, warnings and the temperature bars.
Texts are in Spanish, English or Catalan, chosen from your Home Assistant
language (English otherwise); times use your time zone and 12/24-hour setting.

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
show_warnings: true      # the AEMET banner
show_hourly: true
show_daily: true
hourly_count: 12         # 3–48 hours in the strip
daily_count: 7           # 1–14 days in the list
```

| Option | Default | Meaning |
|---|---|---|
| `entity` | — | The `weather.*` entity of a MeteoVeo config entry. |
| `rain_entity` | found by device | The entry's `binary_sensor` "rain soon" sensor, if you want to point at a different one. |
| `warnings_entity` | found by device | The entry's warnings `sensor`. |
| `show_next_hour` | `true` | Show the next-3-hours rain strip. |
| `show_warnings` | `true` | Show the AEMET warnings banner when a warning is active. |
| `show_hourly` | `true` | Show the hourly strip. |
| `show_daily` | `true` | Show the daily list. |
| `hourly_count` | `12` | Hours in the strip. |
| `daily_count` | `7` | Days in the list (the free level provides 7). |

In a **sections** view the card takes the full width by default and can be
narrowed to half.

## Where the data comes from

The card reads only the integration's entities: the weather entity (current
conditions, and the hourly and daily forecasts over the `weather/subscribe_forecast`
websocket subscription), the "rain soon" binary sensor (the 10-minute steps and
their age) and the warnings sensor. It makes no network requests of its own, and
it loads no code from the internet — it works on an offline Home Assistant.

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
