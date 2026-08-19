"""Credential handling for the MeteoVeo integration.

Two rules shape this module.

**Credentials never travel in the clear.** Uploads go over TLS even though the
service also accepts plain HTTP for consoles that cannot do better.

**Credentials never reach a log.** Home Assistant users routinely paste debug
logs into forum posts and bug reports. The station key is therefore hidden in
``repr``, and :func:`redact` is applied to anything that might contain it
before it is logged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .const import UPLOAD_URL

# Enough characters remain visible to tell two stations apart in a support
# thread, without disclosing anything usable.
_VISIBLE_PREFIX = 3


@dataclass(frozen=True)
class Credentials:
    """Station identifier and key.

    The identifier is not a secret: it appears in the MeteoVeo interface and
    identifies the station in support conversations. The key is a secret and
    is kept out of ``repr`` and ``str``.
    """

    station_id: str
    station_key: str = field(repr=False)

    def __str__(self) -> str:  # pragma: no cover - trivial delegation
        return self.__repr__()


def upload_url_and_params(
    credentials: Credentials,
    fields: Mapping[str, float],
    *,
    now_iso: str,
) -> tuple[str, dict[str, Any]]:
    """Build the upload request.

    The upload protocol carries credentials as request parameters -- that is
    the shape every weather station speaks, and the service accepts nothing
    else on this path. TLS is what protects them, which is why
    :data:`~custom_components.meteoveo.const.UPLOAD_URL` is an ``https`` URL.
    """
    params: dict[str, Any] = {
        "ID": credentials.station_id,
        "PASSWORD": credentials.station_key,
        "dateutc": now_iso,
    }
    params.update(fields)
    return UPLOAD_URL, params


def api_headers(credentials: Credentials) -> dict[str, str]:
    """Headers for read requests.

    Reads authenticate with a header rather than a query parameter: query
    strings end up in proxy logs, browser history and referrer headers, none
    of which are under our control.
    """
    return {
        "Authorization": f"Bearer {credentials.station_id}.{credentials.station_key}",
        "Accept": "application/json",
    }


def _mask(secret: str) -> str:
    if len(secret) <= _VISIBLE_PREFIX:
        return "***"
    return f"{secret[:_VISIBLE_PREFIX]}***"


def redact(text: str, *secrets: str) -> str:
    """Remove credentials from a string before it is logged.

    Explicit ``secrets`` are masked first. Anything that looks like a
    credential-carrying parameter is then masked as well, so a URL that was
    assembled elsewhere cannot slip through.
    """
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, _mask(secret))

    # Catch credential parameters regardless of who built the string.
    out = re.sub(
        r"(?i)\b(password|apikey|api_key|token|key|secret)=([^&\s\"']+)",
        lambda m: f"{m.group(1)}={_mask(m.group(2))}",
        out,
    )
    out = re.sub(
        r"(?i)(authorization:\s*bearer\s+)(\S+)",
        lambda m: f"{m.group(1)}{_mask(m.group(2))}",
        out,
    )
    return out
