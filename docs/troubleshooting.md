# Troubleshooting

## "The station ID or key was not accepted"

- The ID starts with `MV` and is shown on the station's page — it is not
  your e-mail or username.
- The key is the value generated on that same page. **Generating a new key
  invalidates the old one immediately.** If you regenerated the key at any
  point, the copy you saved earlier no longer works — paste the newest one.
- Both fields are trimmed of surrounding whitespace automatically, but a
  character missing from the middle is still a wrong key.

## The integration asks for the key again (re-authentication)

Someone generated a new key on the station's page — perhaps you, on another
device. This is by design: rotating the key is the way to lock out anything
that still uses the old one. Paste the new key and everything resumes.

## "Could not reach MeteoVeo"

Your credentials were **not** tested in this case — do not change them. The
service or your network was unreachable; the integration retries quietly and
recovers on its own. If it persists, check your internet connection and
<https://www.meteoveo.com>.

## Uploads show as accepted but a value looks wrong on the site

The service runs plausibility checks at the point of entry. A reading that
fails them (for example a temperature spike from a failing sensor) is
flagged rather than displayed. The **Sensor problem** binary sensor turns on
when this happens; its attributes say which measurement was flagged.
Common causes are covered in [measurements](measurements.md) — indoor
sensors mapped as outdoor, rain rate mapped as daily rain, absolute
pressure at altitude.

## "Forecast access remaining" is counting down

Your station has stopped reporting regularly. See
[reciprocity](reciprocity.md) for the exact rules. The usual causes:

- Home Assistant restarted and the source entities are `unavailable` —
  readings without a value are not uploaded.
- The mapped entity was renamed or removed. Re-open **Configure** and fix
  the mapping.
- The station itself is offline (power, Wi-Fi).

Access is restored instantly once two readings arrive no more than
10 minutes apart.

## The best-model sensor says "Collecting data"

The service needs several days of readings from your location before it can
say which forecast model performs best there. The sensor's attributes show
how many days are still missing. This is per-station and starts when your
first readings arrive.

## Still stuck?

Open an issue: <https://github.com/meteoveo/ha-meteoveo/issues>. Include the
Home Assistant log lines for `custom_components.meteoveo` — they never
contain your station key.
