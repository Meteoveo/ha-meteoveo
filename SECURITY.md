# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[security advisory](https://github.com/meteoveo/ha-meteoveo/security/advisories/new)
form rather than opening a public issue.

## How this integration handles credentials

- **Transport.** All requests use HTTPS. The service also accepts uploads over
  plain HTTP for weather-station consoles that cannot speak TLS; this
  integration never uses that path.
- **Passwords.** Creating an account, signing in and deleting the account
  send the password to MeteoVeo over HTTPS at that moment only. It is never
  stored, and neither is the account session: it is signed out as soon as
  setup has issued the integration key.
- **Storage.** What is stored lives in the Home Assistant config entry: a
  restricted integration key (reads the forecast for one place; cannot sign
  in, change the account or make purchases), the account's email address,
  the place rounded to about 1 km, and — with a station — the station's
  upload credential. Nothing is written to this repository, to YAML, or to
  any file the integration creates. Diagnostics downloads redact keys, the
  email and the coordinates.
- **Logging.** Keys and passwords are excluded from `repr()` and every log line
  passes through a redaction helper, because debug logs are routinely shared
  in support threads.
- **Scope.** A station credential is limited to that one station: it can
  upload that station's readings and read back data about it. It cannot be
  used to sign in, or to reach any other station or account.

If a station credential is exposed, generate a new one from the station's
settings page; the previous one stops working immediately. If an integration
key is exposed, delete the integration in Home Assistant (which revokes the
key) and set it up again.
