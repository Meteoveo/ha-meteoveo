"""Setup and reconfiguration screens.

The flow has two steps. The first takes the station credentials and checks
them against the service straight away -- a setup that "succeeds" and then
silently uploads nothing would be worse than one that fails on the spot. The
second maps measurements to entities, and every measurement may be left
unset, because not every station has every sensor.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import Credentials
from .client import MeteoVeoClient
from .const import (
    CONF_MEASUREMENTS,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    DOMAIN,
    SIGNUP_URL,
)
from .flow_logic import clean_station_id, entry_title, error_for, unique_id_for
from .selection import NOT_AVAILABLE, validate_selection
from .wu_payload import MEASUREMENTS

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATION_ID): selector.TextSelector(),
        vol.Required(CONF_STATION_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


def _measurement_schema(current: dict[str, str]) -> vol.Schema:
    """One optional entity picker per measurement.

    Every field defaults to "not available": a station without a solar sensor
    must be able to finish setup, and demanding a value for everything is how
    an integration becomes impossible to configure.
    """
    fields: dict[Any, Any] = {}
    for measurement in MEASUREMENTS:
        fields[
            vol.Optional(measurement.key, default=current.get(measurement.key, NOT_AVAILABLE))
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor", "input_number", "number"],
                # Device class narrows the list where we have one; wind
                # direction has no standard class, so that picker stays open.
                **(
                    {"device_class": measurement.device_class}
                    if measurement.device_class
                    else {}
                ),
            )
        )
    return vol.Schema(fields)


async def _verify(hass: Any, credentials: Credentials) -> dict[str, Any]:
    """Ask the service who this station is. Raises on failure."""
    client = MeteoVeoClient(async_get_clientsession(hass), credentials)
    return await client.async_get_station()


class MeteoVeoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a station."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._view: dict[str, Any] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = clean_station_id(user_input[CONF_STATION_ID])
            credentials = Credentials(
                station_id=station_id,
                station_key=user_input[CONF_STATION_KEY].strip(),
            )

            # One entry per station: the id stays stable across key rotations.
            await self.async_set_unique_id(unique_id_for(station_id))
            self._abort_if_unique_id_configured()

            try:
                view = await _verify(self.hass, credentials)
            except Exception as failure:  # noqa: BLE001 - mapped below
                errors["base"] = error_for(failure)
                # The message is logged, never the credentials.
                _LOGGER.debug("station check failed: %s", type(failure).__name__)
            else:
                self._credentials = credentials
                self._view = view
                return await self.async_step_measurements()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={"signup_url": SIGNUP_URL},
        )

    async def async_step_measurements(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._credentials is not None

        if user_input is not None:
            measurements = validate_selection(user_input)
            return self.async_create_entry(
                title=entry_title(self._view, self._credentials.station_id),
                data={
                    CONF_STATION_ID: self._credentials.station_id,
                    CONF_STATION_KEY: self._credentials.station_key,
                },
                options={CONF_MEASUREMENTS: measurements},
            )

        return self.async_show_form(
            step_id="measurements",
            data_schema=_measurement_schema({}),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """A rotated key is re-entered here rather than by reinstalling."""
        self.context["title_placeholders"] = {"name": entry_data.get(CONF_STATION_ID, "")}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            credentials = Credentials(
                station_id=entry.data[CONF_STATION_ID],
                station_key=user_input[CONF_STATION_KEY].strip(),
            )
            try:
                await _verify(self.hass, credentials)
            except Exception as failure:  # noqa: BLE001 - mapped below
                errors["base"] = error_for(failure)
            else:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_STATION_KEY: credentials.station_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return MeteoVeoOptionsFlow()


class MeteoVeoOptionsFlow(OptionsFlow):
    """Change which entity feeds which measurement."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_MEASUREMENTS: validate_selection(user_input)}
            )

        current = self.config_entry.options.get(CONF_MEASUREMENTS, {})
        return self.async_show_form(
            step_id="init",
            data_schema=_measurement_schema(dict(current)),
        )
