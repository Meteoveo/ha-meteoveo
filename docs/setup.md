# Setup guide

This integration brings [MeteoVeo](https://www.meteoveo.com) to Home
Assistant: the forecast for your home in Spain, rain in the next hour and the
official weather warnings. A weather station is optional — if you have one,
the integration can also upload its readings and bring station-specific
extras back.

## Adding the integration

In Home Assistant go to **Settings → Devices & services → Add integration**
and search for **MeteoVeo**. The first screen offers three options.

### Create a free MeteoVeo account

1. Enter your **email** and a **password** of at least 8 characters.
2. Tick **I accept the terms of use and the privacy policy** — required. The
   [terms](https://www.meteoveo.com/legal/terminos) and the
   [privacy policy](https://www.meteoveo.com/legal/privacidad) are linked
   from the form.
3. **Marketing email** is a separate box and stays off unless you tick it.
4. MeteoVeo emails you a **code**; type it in. It can take a minute — check
   the spam folder as well.

If the address already has an account, you receive an email saying so
instead of a code. Close the window and choose **I already have an account**.

No browser is needed at any point.

### I already have an account

Enter your MeteoVeo email and password.

**Account created with Google, Apple or a passkey?** It has no password yet,
so this option cannot sign in. Set a password first in the MeteoVeo app
(**Account → Password**), or use the station-key option below if you have a
station.

### Then: the place

Your Home Assistant home is preselected on the map; drag the pin to change
it. MeteoVeo covers Spain, including the Balearic and Canary Islands, Ceuta
and Melilla. The place is sent and stored rounded to about 1 km — the
forecast does not need your exact address.

The entry and its device are named after the town MeteoVeo resolves the
place to.

### Then: do you have a weather station?

- **No** — setup finishes. You get the forecast entities.
- **Yes** — if your MeteoVeo account already has a station, the next screen
  offers it: **use a station I already have**, or **create a new one**. Picking
  an existing one skips the name and height (the station already has them) and
  goes straight to the measurements.

  ⚠️ **Using an existing station issues it a new upload key**, so Home
  Assistant becomes its uploader. If a console or another program uploads for
  that station today, it stops — and the previous key cannot be shown again.
  Create a new station instead if you want both.

  For a new station: give it a name (only you see it) and the height of its
  temperature sensor above the ground (in cm; usually 150–200), then map
  your measurements: for each one, pick the Home Assistant entity that
  reports it. **Leave a measurement empty if your station does not have that
  sensor.** See [measurements](measurements.md) for what each field expects.
  Readings are uploaded once a minute over HTTPS.

  While the station reports at least every 10 minutes, the account has
  MeteoVeo Plus in the app and on the web as well — see
  [reciprocity](reciprocity.md). Without a station, Plus comes with a subscription;
  the forecast entities are the same.

### I have a station ID and key (advanced)

For a station already set up on meteoveo.com with **direct connection**. The
station page shows a **Station ID** (starts with `MV…`) and lets you generate
a **station key**. Enter both, then map your measurements as above. This is
the setup of version 0.1, unchanged; such an entry now gets the forecast for
the station's place as well.

## What you get

For every entry, on one device:

| Entity | Meaning |
| --- | --- |
| Weather | Current conditions, hourly (48 h) and daily (7 days) forecast. |
| Rain in the next hour | On when rain is expected within 60 minutes. The ten-minute steps are attributes (`band`, `source`, `uncertain`), with `starts_at`, `ends_at`, `issued_at` and `age_minutes`. |
| Rain start / Rain end | When the next rain starts, and when the current rain stops. |
| Weather warnings | Number of active official warnings; `highest_level` and the list as attributes. |

With a station, additionally:

| Entity | Meaning |
| --- | --- |
| Best forecast model | Which forecast model performs best at your station, once enough days of data exist. Until then it shows how many days are still missing; `paused` while the station is silent. |
| Accepted uploads | How many of your uploads the service has accepted. |
| Last upload | When your last reading was accepted. |
| Station extras remaining | How long the station-specific extras last if your station stops reporting. See [reciprocity](reciprocity.md). |
| Sensor problem | On when the service flags one of your readings as implausible. |

The bundled **MeteoVeo card** appears in the dashboard's card picker; there
is nothing to install separately. **Reload the browser once first**
(Ctrl+Shift+R, or *Settings → Companion app → Reset frontend cache* in the
app): the card is registered into the page at load time, so a tab that was
already open — including after a Home Assistant restart — does not have it
yet, and the picker will not list it.

## Changing things later

The integration's **Configure** button offers:

- **Change the place**
- **Station measurements** (entries with a station)
- **Add a weather station** (account entries without one) — it signs you in
  again, because a key that has already been issued cannot be attached to a
  station afterwards; a new one is issued and the entity IDs stay.
- **Delete my MeteoVeo account** — irreversible; asks for your email, your
  password, and your email once more. An App Store or Google Play
  subscription is not cancelled by this; cancel it in the store.

## Security notes

- Everything travels **only over HTTPS**.
- Your **password is never stored**, and neither is the account session.
  Home Assistant keeps a restricted integration key that reads the forecast
  for one place and cannot sign in, change the account or buy anything.
- Passwords, keys and tokens are never written to the Home Assistant log;
  the diagnostics download redacts them, your email and your coordinates.
- If MeteoVeo stops accepting the key, Home Assistant asks you to sign in
  again (re-authentication) instead of failing silently.

If something does not work, see [troubleshooting](troubleshooting.md).
