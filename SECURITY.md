# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[security advisory](https://github.com/meteoveo/ha-meteoveo/security/advisories/new)
form rather than opening a public issue.

## How this integration handles credentials

- **Transport.** All requests use HTTPS. The service also accepts uploads over
  plain HTTP for weather-station consoles that cannot speak TLS; this
  integration never uses that path.
- **Storage.** Credentials live in the Home Assistant config entry and are
  never written to this repository, to YAML, or to any file the integration
  creates.
- **Logging.** The station key is excluded from `repr()` and every log line
  passes through a redaction helper, because debug logs are routinely shared
  in support threads.
- **Scope.** A station credential is limited to that one station: it can
  upload that station's readings and read back data about it. It cannot be
  used to sign in, or to reach any other station or account.

If a credential is exposed, generate a new one from the station's settings
page. The previous one stops working immediately.
