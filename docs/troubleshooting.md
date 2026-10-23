# Troubleshooting

## "Email or password not accepted"

- Check the password; it is case-sensitive.
- An account created with **Google, Apple or a passkey** has no password
  yet, and the integration can only sign in with one. Set a password in the
  MeteoVeo app (**Account → Password**) and try again — or, if you have a
  station already set up on meteoveo.com, use the station-key option.

## The confirmation code does not arrive

It can take a minute; check the spam folder. If the address already has a
MeteoVeo account, you get an email saying so instead of a code — close the
setup window and choose **I already have an account**.

## "MeteoVeo has no forecast there"

The pin is outside the area MeteoVeo covers: Spain, including the Balearic
and Canary Islands, Ceuta and Melilla.

## "This account already has 5 home-automation connections"

Each Home Assistant (or Homey) connection uses one integration key, and an
account can have five. Delete MeteoVeo from a Home Assistant you no longer
use — removing the integration revokes its key — and try again.

## The integration asks me to sign in again

MeteoVeo no longer accepts this connection's key — for example because the
connection was removed from your account elsewhere. Sign in with the same
account; a new key is issued, and the place, the station and the entity IDs
stay as they are.

## The rain entities are unavailable

The place is outside radar nowcast coverage, so there is no next hour to
report. The forecast itself is unaffected.

## "The station ID or key was not accepted"

- The ID starts with `MV` and is shown on the station's page — it is not
  your e-mail or username.
- The key is the value generated on that same page. **Generating a new key
  invalidates the old one immediately.** If you regenerated the key at any
  point, the copy you saved earlier no longer works — paste the newest one.
- Both fields are trimmed of surrounding whitespace automatically, but a
  character missing from the middle is still a wrong key.

## A station-key entry asks for the key again (re-authentication)

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

## "Station extras remaining" is counting down

Your station has stopped reporting regularly. The forecast is not affected;
only the station-specific extras (the best-model verdict) pause after 12
hours. See [reciprocity](reciprocity.md) for the exact rules. The usual
causes:

- Home Assistant restarted and the source entities are `unavailable` —
  readings without a value are not uploaded.
- The mapped entity was renamed or removed. Re-open **Configure** and fix
  the mapping.
- The station itself is offline (power, Wi-Fi).

The extras are restored instantly once two readings arrive no more than
10 minutes apart.

## The best-model sensor says "Collecting data"

The service needs several days of readings from your location before it can
say which forecast model performs best there. The sensor's attributes show
how many days are still missing. This is per-station and starts when your
first readings arrive.

## Still stuck?

Open an issue: <https://github.com/meteoveo/ha-meteoveo/issues>. Include the
Home Assistant log lines for `custom_components.meteoveo` — they never
contain your password or keys — or the integration's diagnostics download,
which redacts keys, your email and your coordinates.
