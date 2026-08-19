# Setup guide

This integration connects a weather station you have registered on
[MeteoVeo](https://www.meteoveo.com) to Home Assistant. It does two things:

- **uploads** the readings you select from your Home Assistant entities to
  MeteoVeo, once a minute, over HTTPS;
- **pulls back** what MeteoVeo derives from them: the best-performing
  forecast model for your location, upload health, and your data-access
  status.

## Before you start

1. Create an account at <https://www.meteoveo.com/#/account>.
2. Add a station there and choose **direct connection**. The station page
   shows a **Station ID** (starts with `MV…`) and lets you generate a
   **station key**.
3. Keep both at hand — the config flow asks for them.

## Adding the integration

1. In Home Assistant go to **Settings → Devices & services → Add
   integration** and search for **MeteoVeo**.
2. Enter the Station ID and the station key. The integration verifies them
   against the service immediately — a setup that "succeeds" and then
   silently uploads nothing would be worse than one that fails on the spot.
3. Map your measurements: for each one, pick the Home Assistant entity that
   reports it. **Leave a measurement empty if your station does not have
   that sensor** — an empty field simply means "not available" and nothing
   is uploaded for it. See [measurements](measurements.md) for what each
   field expects.

You can change the mapping at any time under the integration's
**Configure** button.

## What you get back

| Entity | Meaning |
| --- | --- |
| Best forecast model | Which forecast model performs best at your location, once enough days of data exist. Until then it shows how many days are still missing. |
| Accepted uploads | How many of your uploads the service has accepted. |
| Last upload | When your last reading was accepted. |
| Forecast access remaining | How much of the reciprocity grace window is left if your station stops reporting. See [reciprocity](reciprocity.md). |
| Sensor problem | On when the service flags one of your readings as implausible. |

## Security notes

- Credentials travel **only over HTTPS**. The plain-HTTP hostname that
  exists for TLS-incapable station consoles is not used by this
  integration.
- The station key is never written to the Home Assistant log.
- Generating a new key on the station page invalidates the old one
  immediately; the integration will prompt for the new key
  (re-authentication) instead of failing silently.

If something does not work, see [troubleshooting](troubleshooting.md).
