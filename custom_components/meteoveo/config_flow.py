"""Setup, re-authentication and options screens.

Setup starts with a choice:

* **Create an account** -- email, password, the terms, an emailed code.
* **I already have an account** -- email and password.
* **I have a station key** (advanced) -- the 0.1.x route, unchanged.

The first two continue with the place (the Home Assistant home by default)
and an optional weather station. What is stored afterwards is a restricted
integration key that reads the forecast for that one place -- never the
password, and never the account's session token, which is used only while
the flow is open and then signed out.

Every check against the service happens while the person is still on the
screen: a setup that "succeeds" and then silently does nothing would be worse
than one that fails on the spot.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.translation import async_get_translations

from .auth import Credentials
from .client import (
    AccountClient,
    ApiError,
    InvalidCredentials,
    MeteoVeoClient,
    MeteoVeoError,
    ServiceUnavailable,
)
from .const import (
    CONF_EMAIL,
    CONF_INTEGRATION_KEY,
    CONF_KEY_ID,
    CONF_MEASUREMENTS,
    CONF_PRESSURE_KIND,
    CONF_STATION_ID,
    CONF_STATION_KEY,
    CONF_STATION_REF,
    DEFAULT_SENSOR_HEIGHT_CM,
    DOCS_MEASUREMENTS_URL,
    DOCS_RECIPROCITY_URL,
    DOCS_SETUP_URL,
    DOCS_TROUBLESHOOTING_URL,
    DOMAIN,
    MAX_SENSOR_HEIGHT_CM,
    MIN_SENSOR_HEIGHT_CM,
    PRIVACY_URL,
    SIGNUP_URL,
    TERMS_URL,
)
from .flow_logic import (
    api_language,
    clean_station_id,
    entry_title,
    error_for,
    has_station,
    in_service_area,
    is_account_entry,
    looks_like_email,
    place_title,
    same_email,
    unique_id_for,
)
from .selection import split_pressure_kind, validate_selection
from .wu_payload import MEASUREMENTS, PRESSURE_ABSOLUTE, PRESSURE_KINDS

_LOGGER = logging.getLogger(__name__)

# The service's minimum, checked here as well so the form can say so at once.
MIN_PASSWORD_LENGTH = 8

CONF_ACCEPT_TERMS = "accept_terms"
CONF_MARKETING = "marketing"
CONF_CODE = "code"
CONF_HAS_STATION = "has_station"
CONF_STATION_NAME = "station_name"
CONF_SENSOR_HEIGHT = "sensor_height_cm"
CONF_CONFIRM = "confirm"
# MeteoVeo ADR-0872: latszik-e az allomas a nyilvanos terkepen es a kozeli-listakon.
CONF_PUBLIC_DISPLAY = "public_display"
# MeteoVeo ADR-0866 D12: melyik MEGLEVO allomast kotjuk be.
CONF_STATION_CHOICE = "station"

_EMAIL = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL, autocomplete="username")
)
_CURRENT_PASSWORD = selector.TextSelector(
    selector.TextSelectorConfig(
        type=selector.TextSelectorType.PASSWORD, autocomplete="current-password"
    )
)
_NEW_PASSWORD = selector.TextSelector(
    selector.TextSelectorConfig(
        type=selector.TextSelectorType.PASSWORD, autocomplete="new-password"
    )
)
_LOCATION = selector.LocationSelector(selector.LocationSelectorConfig(radius=False))

STEP_STATION_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATION_ID): selector.TextSelector(),
        vol.Required(CONF_STATION_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)

STEP_LOGIN_SCHEMA = vol.Schema(
    {vol.Required(CONF_EMAIL): _EMAIL, vol.Required(CONF_PASSWORD): _CURRENT_PASSWORD}
)


def _measurement_schema(
    current: dict[str, str], pressure_kind: str = PRESSURE_ABSOLUTE
) -> vol.Schema:
    """One optional entity picker per measurement.

    Every field defaults to "not available": a station without a solar sensor
    must be able to finish setup, and demanding a value for everything is how
    an integration becomes impossible to configure.

    One field is not an entity: how the barometer reports (MeteoVeo ADR-0844).
    It sits directly under the pressure picker, because that is the only place
    where the question makes sense -- asked anywhere else it would be missed,
    and the answer changes what the number means.
    """
    fields: dict[Any, Any] = {}
    for measurement in MEASUREMENTS:
        # No default. An entity picker rejects any placeholder value, so
        # "not available" is expressed the way Home Assistant expresses it:
        # the field is simply left empty. A previously chosen entity is
        # offered back as a suggestion rather than as a hard default, so it
        # can be cleared again.
        chosen = current.get(measurement.key)
        field = (
            vol.Optional(measurement.key, description={"suggested_value": chosen})
            if chosen
            else vol.Optional(measurement.key)
        )
        fields[field] = selector.EntitySelector(
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
        if measurement.sea_level_api_field:
            fields[vol.Required(CONF_PRESSURE_KIND, default=pressure_kind)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(PRESSURE_KINDS),
                        translation_key=CONF_PRESSURE_KIND,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
    return vol.Schema(fields)


def _station_choice_schema(stations: list[dict[str, Any]]) -> vol.Schema:
    """Pick one of the account's own stations (MeteoVeo ADR-0866 D12).

    The labels are the station's own name and town, so they need no
    translation; the step's prose does, and that lives in `strings.json`.
    """
    options = [
        selector.SelectOptionDict(
            value=str(station["id"]),
            label=" — ".join(
                part for part in (station.get("name"), station.get("town")) if part
            )
            or str(station["id"]),
        )
        for station in stations
    ]
    return vol.Schema(
        {
            vol.Required(CONF_STATION_CHOICE, default=options[0]["value"]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options, mode=selector.SelectSelectorMode.LIST
                )
            )
        }
    )


async def _own_stations(account: AccountClient, token: str) -> list[dict[str, Any]]:
    """The account's stations, or an empty list if we could not ask.

    A failed listing must not block setting up a station: without it the flow
    simply offers what it always offered -- creating a new one.
    """
    try:
        return await account.async_list_stations(token)
    except MeteoVeoError:
        _LOGGER.debug("the account's stations could not be listed")
        return []


def _station_details_schema(name: str, sensor_height_cm: int) -> vol.Schema:
    """Name and sensor height. Used by setup and by the Options door alike."""
    return vol.Schema(
        {
            vol.Required(CONF_STATION_NAME, default=name): selector.TextSelector(),
            vol.Required(CONF_SENSOR_HEIGHT, default=sensor_height_cm): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SENSOR_HEIGHT_CM,
                    max=MAX_SENSOR_HEIGHT_CM,
                    step=1,
                    unit_of_measurement="cm",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _location_schema(lat: float, lon: float) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_LOCATION, default={CONF_LATITUDE: lat, CONF_LONGITUDE: lon}
            ): _LOCATION
        }
    )


def _station_place(hass: HomeAssistant, place_lat: float, place_lon: float) -> tuple[float, float]:
    """The station's coordinates: Home Assistant's own home position when it agrees
    with the configured place (within ~2 km), otherwise that place.

    Rounded to 4 decimals (~11 m), exactly as the setup flow stores it.
    """
    home_lat = hass.config.latitude
    home_lon = hass.config.longitude
    if home_lat is not None and home_lon is not None:
        # Fokokban merve: 0,02 fok szelesseg ~2,2 km, es a hosszusagot a szelessegen
        # nem szukitjuk - egy nagyvonalu kor eleg, a kapu nem pontossagi mertek.
        if abs(home_lat - place_lat) <= 0.02 and abs(home_lon - place_lon) <= 0.03:
            return round(float(home_lat), 4), round(float(home_lon), 4)
    return round(place_lat, 4), round(place_lon, 4)


def _key_place(lat: float, lon: float) -> tuple[float, float]:
    """The place as the integration key gets it: ~1 km, like the service stores it.

    The forecast does not need the exact position of someone's home, so the
    exact position is never sent for it.
    """
    return round(lat, 2), round(lon, 2)


async def _verify(hass: Any, credentials: Credentials) -> dict[str, Any]:
    """Ask the service who this station is. Raises on failure."""
    client = MeteoVeoClient(async_get_clientsession(hass), credentials)
    return await client.async_get_station()


def _account(hass: HomeAssistant) -> AccountClient:
    return AccountClient(async_get_clientsession(hass))


def _account_error(failure: BaseException) -> str:
    """Error key for an account request that failed without a specific code."""
    if isinstance(failure, InvalidCredentials):
        return "invalid_login"
    if isinstance(failure, ServiceUnavailable):
        return "cannot_connect"
    return "unknown"


class MeteoVeoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add MeteoVeo."""

    VERSION = 1

    def __init__(self) -> None:
        # Station-key route.
        self._credentials: Credentials | None = None
        self._view: dict[str, Any] | None = None
        # Account route. The password is kept only between the sign-up form
        # and the code form (the sign-in after the code needs it); the token
        # only until the entry is created. Neither is ever stored.
        self._email: str | None = None
        self._password: str | None = None
        self._verified = False
        self._token: str | None = None
        self._lat: float | None = None
        self._lon: float | None = None
        self._want_station = False
        self._station_name: str | None = None
        self._sensor_height_cm = DEFAULT_SENSOR_HEIGHT_CM
        self._measurements: dict[str, str] = {}
        self._pressure_kind = PRESSURE_ABSOLUTE
        self._station: dict[str, Any] | None = None
        # ADR-0866 D12: a fiok meglevo allomasai, es amelyiket bekotjuk.
        self._stations: list[dict[str, Any]] = []
        self._adopt_station_id: int | None = None

    # --- Entry point ------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user",
            menu_options=["create_account", "login", "station_key"],
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    # --- Station key (advanced; the 0.1.x route) --------------------------

    async def async_step_station_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
            step_id="station_key",
            data_schema=STEP_STATION_KEY_SCHEMA,
            errors=errors,
            description_placeholders={
                "signup_url": SIGNUP_URL,
                "docs_url": DOCS_SETUP_URL,
            },
        )

    async def async_step_measurements(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            answers, self._pressure_kind = split_pressure_kind(user_input)
            measurements = validate_selection(answers)
            if self._token is not None:
                self._measurements = measurements
                return await self._async_finish_account(self._show_measurements)
            assert self._credentials is not None
            return self.async_create_entry(
                title=entry_title(self._view, self._credentials.station_id),
                data={
                    CONF_STATION_ID: self._credentials.station_id,
                    CONF_STATION_KEY: self._credentials.station_key,
                },
                options={
                    CONF_MEASUREMENTS: measurements,
                    CONF_PRESSURE_KIND: self._pressure_kind,
                },
            )
        return self._show_measurements({})

    def _show_measurements(self, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="measurements",
            data_schema=self.add_suggested_values_to_schema(
                _measurement_schema({}, self._pressure_kind), self._measurements
            ),
            errors=errors,
            description_placeholders={"docs_url": DOCS_MEASUREMENTS_URL},
        )

    # --- New account ------------------------------------------------------

    async def async_step_create_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            marketing = bool(user_input.get(CONF_MARKETING, False))
            suggested = {CONF_EMAIL: email, CONF_MARKETING: marketing}
            if not looks_like_email(email):
                errors[CONF_EMAIL] = "invalid_email"
            if len(password) < MIN_PASSWORD_LENGTH:
                errors[CONF_PASSWORD] = "password_too_short"
            if not user_input.get(CONF_ACCEPT_TERMS):
                errors[CONF_ACCEPT_TERMS] = "terms_required"

            if not errors:
                try:
                    await _account(self.hass).async_signup(
                        email,
                        password,
                        marketing=marketing,
                        lang=api_language(self.hass.config.language),
                    )
                except ApiError as failure:
                    if failure.code == "registration_closed":
                        return self.async_abort(reason="registration_closed")
                    if failure.code == "weak_password":
                        errors[CONF_PASSWORD] = "weak_password"
                    else:
                        errors["base"] = "unknown"
                except MeteoVeoError as failure:
                    errors["base"] = _account_error(failure)
                else:
                    self._email = email
                    self._password = password
                    self._verified = False
                    return await self.async_step_verify_code()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): _EMAIL,
                vol.Required(CONF_PASSWORD): _NEW_PASSWORD,
                vol.Required(CONF_ACCEPT_TERMS, default=False): selector.BooleanSelector(),
                vol.Optional(CONF_MARKETING, default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="create_account",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders={
                "terms_url": TERMS_URL,
                "privacy_url": PRIVACY_URL,
                "docs_url": DOCS_SETUP_URL,
            },
        )

    async def async_step_verify_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._email is not None and self._password is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            code = "".join(user_input[CONF_CODE].split())
            account = _account(self.hass)
            try:
                # A code is single-use: after it was accepted once, a retry
                # (say, because the sign-in after it timed out) signs in only.
                if not self._verified:
                    await account.async_verify(self._email, code)
                    self._verified = True
                token = await account.async_login(self._email, self._password)
            except ApiError as failure:
                if failure.code == "invalid_code":
                    errors[CONF_CODE] = "invalid_code"
                else:
                    errors["base"] = "unknown"
            except MeteoVeoError as failure:
                errors["base"] = _account_error(failure)
            else:
                self._token = token
                self._password = None
                return await self.async_step_location()

        return self.async_show_form(
            step_id="verify_code",
            data_schema=vol.Schema(
                {
                    # The code is digits only (6, valid 24 h): "tel" brings up the
                    # number pad on phones and, unlike "number", keeps leading
                    # zeros. It still accepts letters, so older codes work too.
                    vol.Required(CONF_CODE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEL,
                            autocomplete="one-time-code",
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"email": self._email, "docs_url": DOCS_SETUP_URL},
        )

    # --- Existing account -------------------------------------------------

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            suggested = {CONF_EMAIL: email}
            try:
                token = await _account(self.hass).async_login(email, user_input[CONF_PASSWORD])
            except MeteoVeoError as failure:
                errors["base"] = _account_error(failure)
            else:
                self._email = email
                self._token = token
                return await self.async_step_location()

        return self.async_show_form(
            step_id="login",
            data_schema=self.add_suggested_values_to_schema(STEP_LOGIN_SCHEMA, suggested),
            errors=errors,
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    # --- Place and station (both account routes) ---------------------------

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        lat = self._lat if self._lat is not None else self.hass.config.latitude
        lon = self._lon if self._lon is not None else self.hass.config.longitude

        if user_input is not None:
            lat = float(user_input[CONF_LOCATION][CONF_LATITUDE])
            lon = float(user_input[CONF_LOCATION][CONF_LONGITUDE])
            if in_service_area(lat, lon):
                self._lat, self._lon = lat, lon
                return await self.async_step_has_station()
            errors[CONF_LOCATION] = "invalid_location"

        return self._show_location(lat, lon, errors)

    def _show_location(self, lat: float, lon: float, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="location",
            data_schema=_location_schema(lat, lon),
            errors=errors,
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    async def async_step_has_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._want_station = bool(user_input[CONF_HAS_STATION])
            if self._want_station:
                return await self.async_step_station_pick()
            return await self._async_finish_account(self._show_has_station)
        return self._show_has_station({})

    def _show_has_station(self, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="has_station",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HAS_STATION, default=self._want_station
                    ): selector.BooleanSelector()
                }
            ),
            errors=errors,
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    async def async_step_station_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Use a station the account already has, or make a new one (D12).

        Someone who registered their station on the web or in the app used to
        have no way in here: the only door CREATED a station, so they either
        ended up with a duplicate or with no station on the entry at all. The
        menu is only shown when there is something to choose from -- with no
        stations the flow goes straight on, as it always did.
        """
        assert self._token is not None
        self._stations = await _own_stations(_account(self.hass), self._token)
        if not self._stations:
            return await self.async_step_station_details()
        return self.async_show_menu(
            step_id="station_pick",
            menu_options=["station_existing", "station_details"],
        )

    async def async_step_station_existing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Which existing station -- and what adopting it costs (D13)."""
        if user_input is not None:
            self._adopt_station_id = int(user_input[CONF_STATION_CHOICE])
            # Name and sensor height already exist on the station: asking for
            # them again could only produce a second, disagreeing answer.
            return await self.async_step_measurements()
        return self.async_show_form(
            step_id="station_existing",
            data_schema=_station_choice_schema(self._stations),
            description_placeholders={"docs_url": DOCS_MEASUREMENTS_URL},
        )

    async def async_step_station_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._station_name = user_input[CONF_STATION_NAME].strip()
            self._sensor_height_cm = int(user_input[CONF_SENSOR_HEIGHT])
            return await self.async_step_measurements()
        # A menu-bol ide lepve UJ allomast akar: egy korabbi valasztas ne
        # maradjon be.
        self._adopt_station_id = None

        return self.async_show_form(
            step_id="station_details",
            data_schema=_station_details_schema(
                self._station_name or self.hass.config.location_name or "",
                self._sensor_height_cm,
            ),
            description_placeholders={"docs_url": DOCS_MEASUREMENTS_URL},
        )

    async def _async_finish_account(self, show_again) -> ConfigFlowResult:
        """Create the station (if wanted) and the integration key; store the entry."""
        assert self._token and self._email and self._lat is not None and self._lon is not None
        account = _account(self.hass)
        key_lat, key_lon = _key_place(self._lat, self._lon)
        try:
            # Created once: if the key request fails and the person retries,
            # the station made on the first attempt is reused, not duplicated.
            if self._want_station and self._station is None:
                self._station = (
                    # ADR-0866 D13: a bekotes UJ bekuldesi kulcsot ad (forgatas).
                    await account.async_adopt_station(self._token, self._adopt_station_id)
                    if self._adopt_station_id is not None
                    else await account.async_create_station(
                        self._token,
                        name=self._station_name or self.hass.config.location_name or "Home",
                        lat=round(self._lat, 4),
                        lon=round(self._lon, 4),
                        sensor_height_cm=self._sensor_height_cm,
                    )
                )
            station = self._station if self._want_station else None
            issued = await account.async_create_integration_key(
                self._token,
                lat=key_lat,
                lon=key_lon,
                label=self.hass.config.location_name,
                station_ref=station["stationId"] if station else None,
            )
        except ApiError as failure:
            if failure.code == "invalid_location":
                return self._show_location(self._lat, self._lon, {CONF_LOCATION: "invalid_location"})
            if failure.code == "too_many_keys":
                return self.async_abort(reason="too_many_keys")
            return show_again({"base": "unknown"})
        except InvalidCredentials:
            # The session ran out while the flow sat open.
            return self.async_abort(reason="session_expired")
        except MeteoVeoError as failure:
            return show_again({"base": _account_error(failure)})

        await self.async_set_unique_id(str(issued["keyId"]))
        self._abort_if_unique_id_configured()

        # The session token's job is done: forget it. It is a short-lived
        # sign-in token without a refresh token, so there is nothing to revoke.
        self._token = None

        place = issued.get("place") if isinstance(issued.get("place"), dict) else {}
        data: dict[str, Any] = {
            CONF_INTEGRATION_KEY: issued["key"],
            CONF_KEY_ID: str(issued["keyId"]),
            CONF_EMAIL: self._email,
            CONF_LATITUDE: place.get("lat", key_lat),
            CONF_LONGITUDE: place.get("lon", key_lon),
        }
        options: dict[str, Any] = {}
        if station:
            data[CONF_STATION_ID] = station["ingestId"]
            data[CONF_STATION_KEY] = station["secret"]
            data[CONF_STATION_REF] = station["stationId"]
            options[CONF_MEASUREMENTS] = self._measurements
            options[CONF_PRESSURE_KIND] = self._pressure_kind
        return self.async_create_entry(
            title=place_title(place, self.hass.config.location_name or "MeteoVeo"),
            data=data,
            options=options,
        )

    # --- Re-authentication -------------------------------------------------

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """A rejected credential is replaced here rather than by reinstalling."""
        if is_account_entry(entry_data):
            self.context["title_placeholders"] = {"name": self._get_reauth_entry().title}
            return await self.async_step_reauth_login()
        self.context["title_placeholders"] = {"name": entry_data.get(CONF_STATION_ID, "")}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
            description_placeholders={"docs_url": DOCS_TROUBLESHOOTING_URL},
        )

    async def async_step_reauth_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in again; a new integration key replaces the rejected one.

        The place and the station stay as they were. If the station's upload
        key was what got rejected, a new one is issued as well.
        """
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        suggested = {CONF_EMAIL: entry.data.get(CONF_EMAIL, "")}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            suggested = {CONF_EMAIL: email}
            if not same_email(email, entry.data.get(CONF_EMAIL)):
                errors[CONF_EMAIL] = "wrong_account"
            else:
                try:
                    updates = await self._async_renew(entry, email, user_input[CONF_PASSWORD])
                except ApiError as failure:
                    if failure.code == "too_many_keys":
                        return self.async_abort(reason="too_many_keys")
                    errors["base"] = "unknown"
                except MeteoVeoError as failure:
                    errors["base"] = _account_error(failure)
                else:
                    return self.async_update_reload_and_abort(
                        entry, data={**entry.data, **updates}
                    )

        return self.async_show_form(
            step_id="reauth_login",
            data_schema=self.add_suggested_values_to_schema(STEP_LOGIN_SCHEMA, suggested),
            errors=errors,
            description_placeholders={"docs_url": DOCS_TROUBLESHOOTING_URL},
        )

    async def _async_renew(
        self, entry: ConfigEntry, email: str, password: str
    ) -> dict[str, Any]:
        account = _account(self.hass)
        token = await account.async_login(email, password)
        updates: dict[str, Any] = {}
        station_ref = entry.data.get(CONF_STATION_REF)
        if has_station(entry.data) and station_ref is not None:
            try:
                await _verify(
                    self.hass,
                    Credentials(
                        station_id=entry.data[CONF_STATION_ID],
                        station_key=entry.data[CONF_STATION_KEY],
                    ),
                )
            except InvalidCredentials:
                renewed = await account.async_renew_ingest_key(token, station_ref)
                updates[CONF_STATION_KEY] = renewed["secret"]
                if renewed.get("ingestId"):
                    updates[CONF_STATION_ID] = renewed["ingestId"]

        # The old key goes first, so it does not count against the
        # per-account limit. Revoking an already revoked key is a no-op.
        try:
            await account.async_delete_integration_key(token, entry.data[CONF_KEY_ID])
        except ServiceUnavailable:
            pass
        issued = await account.async_create_integration_key(
            token,
            lat=entry.data[CONF_LATITUDE],
            lon=entry.data[CONF_LONGITUDE],
            label=self.hass.config.location_name,
            station_ref=station_ref if has_station(entry.data) else None,
        )
        updates[CONF_INTEGRATION_KEY] = issued["key"]
        updates[CONF_KEY_ID] = str(issued["keyId"])
        return updates

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return MeteoVeoOptionsFlow()


class MeteoVeoOptionsFlow(OptionsFlow):
    """Place, measurement mapping, adding a station, and deleting the account."""

    def __init__(self) -> None:
        # Only while the "add a station" flow is open, and never stored: the
        # session token, what the station is called, and the station the
        # service made from it (so a retry does not make a second one).
        self._token: str | None = None
        self._station_name: str | None = None
        self._sensor_height_cm = DEFAULT_SENSOR_HEIGHT_CM
        self._station: dict[str, Any] | None = None
        # ADR-0866 D12: a fiok meglevo allomasai, es amelyiket bekotjuk.
        self._stations: list[dict[str, Any]] = []
        self._adopt_station_id: int | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        data = self.config_entry.data
        options: list[str] = []
        if is_account_entry(data):
            options.append("location")
        if has_station(data):
            options.append("measurements")
            # ADR-0872: the public-visibility switch belongs with the station,
            # so it is only offered when there is one.
            options.append("visibility")
        elif is_account_entry(data):
            # ADR-0866 D9: the station door, for someone who said no at
            # setup or had no station then. With a station there is nothing
            # to add -- the measurements are what changes.
            options.append("add_station")
        if is_account_entry(data):
            options.append("delete_account")
        return self.async_show_menu(
            step_id="init",
            menu_options=options,
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    async def async_step_visibility(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Public visibility of the station (MeteoVeo ADR-0872).

        The current state comes from the service rather than from the entry:
        the same switch exists on the website, and a stale copy here would
        quietly undo a change made there.
        """
        entry = self.config_entry
        errors: dict[str, str] = {}
        client = MeteoVeoClient(
            async_get_clientsession(self.hass),
            credentials=Credentials(
                station_id=str(entry.data[CONF_STATION_ID]),
                station_key=str(entry.data[CONF_STATION_KEY]),
            ),
        )

        if user_input is not None:
            try:
                await client.async_set_visibility(bool(user_input[CONF_PUBLIC_DISPLAY]))
            except InvalidCredentials:
                entry.async_start_reauth(self.hass)
                return self.async_abort(reason="reauth_required")
            except MeteoVeoError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(data=dict(entry.options))

        current = True
        if not errors:
            try:
                station = await client.async_get_station()
            except InvalidCredentials:
                entry.async_start_reauth(self.hass)
                return self.async_abort(reason="reauth_required")
            except MeteoVeoError:
                errors["base"] = "cannot_connect"
            else:
                current = station.get("publicDisplay", True) is not False
        else:
            current = bool(user_input[CONF_PUBLIC_DISPLAY]) if user_input else True

        return self.async_show_form(
            step_id="visibility",
            data_schema=vol.Schema(
                {vol.Required(CONF_PUBLIC_DISPLAY, default=current): selector.BooleanSelector()}
            ),
            errors=errors,
            # The reciprocity page is the one that says switching this off does
            # NOT take Plus away -- which is the question people ask here.
            description_placeholders={"docs_url": DOCS_RECIPROCITY_URL},
        )

    async def async_step_measurements(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            answers, pressure_kind = split_pressure_kind(user_input)
            selection = validate_selection(answers)
            if self._token is not None:
                # The "add a station" flow ends here: the station and the new
                # key are created only once the mapping is known, so an
                # abandoned flow leaves nothing behind on the account.
                return await self._async_attach_station(selection, pressure_kind)
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_MEASUREMENTS: selection,
                    CONF_PRESSURE_KIND: pressure_kind,
                }
            )

        current = self.config_entry.options.get(CONF_MEASUREMENTS, {})
        return self._show_measurements(dict(current), {})

    def _show_measurements(
        self,
        current: dict[str, str],
        errors: dict[str, str],
        pressure_kind: str | None = None,
    ) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="measurements",
            data_schema=_measurement_schema(
                current,
                pressure_kind
                or self.config_entry.options.get(CONF_PRESSURE_KIND, PRESSURE_ABSOLUTE),
            ),
            errors=errors,
            description_placeholders={"docs_url": DOCS_MEASUREMENTS_URL},
        )

    # --- Adding a station afterwards (ADR-0866 D9) -------------------------

    async def async_step_add_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in, then reuse the station steps of the setup flow.

        Signing in is not a formality: the service only ever creates or
        revokes an integration key, it does not attach a station to one that
        was already issued -- so a new key is needed, and issuing one is an
        account-level action. The integration key deliberately cannot do it,
        which is also why a leaked key could not put a station on an account.
        """
        entry = self.config_entry
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {CONF_EMAIL: entry.data.get(CONF_EMAIL, "")}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            suggested = {CONF_EMAIL: email}
            if not same_email(email, entry.data.get(CONF_EMAIL)):
                errors[CONF_EMAIL] = "wrong_account"
            else:
                try:
                    self._token = await _account(self.hass).async_login(
                        email, user_input[CONF_PASSWORD]
                    )
                except MeteoVeoError as failure:
                    errors["base"] = _account_error(failure)
                else:
                    return await self.async_step_station_pick()

        return self.async_show_form(
            step_id="add_station",
            data_schema=self.add_suggested_values_to_schema(STEP_LOGIN_SCHEMA, suggested),
            errors=errors,
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    async def async_step_station_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ugyanaz a valasztas, mint a varazsloban (ADR-0866 D12)."""
        assert self._token is not None
        self._stations = await _own_stations(_account(self.hass), self._token)
        if not self._stations:
            return await self.async_step_station_details()
        return self.async_show_menu(
            step_id="station_pick",
            menu_options=["station_existing", "station_details"],
        )

    async def async_step_station_existing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._adopt_station_id = int(user_input[CONF_STATION_CHOICE])
            return await self.async_step_measurements()
        return self.async_show_form(
            step_id="station_existing",
            data_schema=_station_choice_schema(self._stations),
            description_placeholders={"docs_url": DOCS_MEASUREMENTS_URL},
        )

    async def async_step_station_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._station_name = user_input[CONF_STATION_NAME].strip()
            self._sensor_height_cm = int(user_input[CONF_SENSOR_HEIGHT])
            return await self.async_step_measurements()
        self._adopt_station_id = None
        return self.async_show_form(
            step_id="station_details",
            data_schema=_station_details_schema(
                self._station_name or self.hass.config.location_name or "",
                self._sensor_height_cm,
            ),
            description_placeholders={"docs_url": DOCS_MEASUREMENTS_URL},
        )

    async def _async_attach_station(
        self, measurements: dict[str, str], pressure_kind: str = PRESSURE_ABSOLUTE
    ) -> ConfigFlowResult:
        """Create the station, swap the key for one bound to it, reload."""
        entry = self.config_entry
        assert self._token is not None
        account = _account(self.hass)
        # The place is the one the entry already has: the forecast and the
        # station belong to the same spot, and asking for a pin again here
        # would invite two different answers for one home.
        lat = float(entry.data[CONF_LATITUDE])
        lon = float(entry.data[CONF_LONGITUDE])
        # THE STATION'S OWN POSITION, not the entry's place (ADR-0866 D9).
        #
        # The entry keeps the place ROUNDED to 0.01 degrees (~1 km) - it only has to
        # pick a forecast point. A station is a measurement: its coordinates end up in
        # the radar-gauge pairing and in the neighbour logic, so a kilometre of error
        # is not a cosmetic matter. The setup flow therefore stores 4 decimals (~11 m)
        # of the pin the person placed, and that pin is gone by the time this option
        # runs.
        #
        # Home Assistant's own home coordinates are precise and are where the station
        # almost always stands - but only if they agree with the configured place. The
        # guard is the rounding itself: within ~2 km we trust the home position, beyond
        # it we keep the entry's place rather than move someone's station silently.
        station_lat, station_lon = _station_place(self.hass, lat, lon)
        try:
            # Created once: a retry after a failed key request reuses it
            # rather than leaving a second station on the account.
            if self._station is None:
                self._station = (
                    # ADR-0866 D13: a bekotes UJ bekuldesi kulcsot ad (forgatas).
                    await account.async_adopt_station(self._token, self._adopt_station_id)
                    if self._adopt_station_id is not None
                    else await account.async_create_station(
                        self._token,
                        name=self._station_name or self.hass.config.location_name or "Home",
                        lat=station_lat,
                        lon=station_lon,
                        sensor_height_cm=self._sensor_height_cm,
                    )
                )
            # The new key first, the old one after: if this fails, the entry
            # still has a key that works.
            issued = await account.async_create_integration_key(
                self._token,
                lat=lat,
                lon=lon,
                label=self.hass.config.location_name,
                station_ref=self._station["stationId"],
            )
        except ApiError as failure:
            if failure.code == "too_many_keys":
                return self.async_abort(reason="too_many_keys")
            return self._show_measurements(measurements, {"base": "unknown"}, pressure_kind)
        except InvalidCredentials:
            # The sign-in ran out while the flow sat open.
            return self.async_abort(reason="session_expired")
        except MeteoVeoError as failure:
            return self._show_measurements(
                measurements, {"base": _account_error(failure)}, pressure_kind
            )

        try:
            await account.async_delete_integration_key(self._token, entry.data[CONF_KEY_ID])
        except MeteoVeoError:
            # An orphaned key shows up as unused on the service side and can
            # be removed there; failing the whole flow over it would be worse.
            _LOGGER.debug("the previous integration key could not be revoked")
        self._token = None

        station = self._station
        self.hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_INTEGRATION_KEY: issued["key"],
                CONF_KEY_ID: str(issued["keyId"]),
                CONF_STATION_ID: station["ingestId"],
                CONF_STATION_KEY: station["secret"],
                CONF_STATION_REF: station["stationId"],
            },
        )
        # Writing the options reloads the entry, which starts the uploads and
        # creates the station entities.
        return self.async_create_entry(
            data={
                **entry.options,
                CONF_MEASUREMENTS: measurements,
                CONF_PRESSURE_KIND: pressure_kind,
            }
        )

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        lat = entry.data.get(CONF_LATITUDE, self.hass.config.latitude)
        lon = entry.data.get(CONF_LONGITUDE, self.hass.config.longitude)

        if user_input is not None:
            lat = float(user_input[CONF_LOCATION][CONF_LATITUDE])
            lon = float(user_input[CONF_LOCATION][CONF_LONGITUDE])
            if not in_service_area(lat, lon):
                errors[CONF_LOCATION] = "invalid_location"
            else:
                key_lat, key_lon = _key_place(lat, lon)
                client = MeteoVeoClient(
                    async_get_clientsession(self.hass),
                    integration_key=entry.data[CONF_INTEGRATION_KEY],
                )
                try:
                    place = await client.async_set_location(key_lat, key_lon)
                except InvalidCredentials:
                    entry.async_start_reauth(self.hass)
                    return self.async_abort(reason="reauth_required")
                except ApiError as failure:
                    if failure.code == "invalid_location":
                        errors[CONF_LOCATION] = "invalid_location"
                    elif failure.code == "location_change_limit":
                        # ADR-0834 D2: at most 3 changes a day and 10 a month.
                        errors["base"] = "location_change_limit"
                    else:
                        errors["base"] = "unknown"
                except MeteoVeoError as failure:
                    errors["base"] = _account_error(failure)
                else:
                    # The data change reloads the entry, which fetches the
                    # forecast for the new place.
                    self.hass.config_entries.async_update_entry(
                        entry,
                        title=place_title(place, entry.title),
                        data={
                            **entry.data,
                            CONF_LATITUDE: place.get("lat", key_lat),
                            CONF_LONGITUDE: place.get("lon", key_lon),
                        },
                    )
                    return self.async_create_entry(data=dict(entry.options))

        return self.async_show_form(
            step_id="location",
            data_schema=_location_schema(lat, lon),
            errors=errors,
            description_placeholders={"docs_url": DOCS_SETUP_URL},
        )

    async def async_step_delete_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete the MeteoVeo account. Irreversible, so it asks for proof."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {CONF_EMAIL: entry.data.get(CONF_EMAIL, "")}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            confirm = user_input[CONF_CONFIRM].strip()
            password = user_input[CONF_PASSWORD]
            suggested = {CONF_EMAIL: email}
            if not same_email(email, entry.data.get(CONF_EMAIL)):
                errors[CONF_EMAIL] = "wrong_account"
            elif not same_email(confirm, email):
                errors[CONF_CONFIRM] = "confirm_mismatch"
            else:
                account = _account(self.hass)
                try:
                    token = await account.async_login(email, password)
                    await account.async_delete_account(token, password=password, confirm=confirm)
                except ApiError as failure:
                    field, key = {
                        "invalid_password": (CONF_PASSWORD, "invalid_password"),
                        "confirm_mismatch": (CONF_CONFIRM, "confirm_mismatch"),
                        "password_required": ("base", "password_required"),
                    }.get(failure.code or "", ("base", "unknown"))
                    errors[field] = key
                except MeteoVeoError as failure:
                    errors["base"] = _account_error(failure)
                else:
                    await _async_after_account_deleted(self.hass, email)
                    return self.async_abort(reason="account_deleted")

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): _EMAIL,
                vol.Required(CONF_PASSWORD): _CURRENT_PASSWORD,
                vol.Required(CONF_CONFIRM): selector.TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="delete_account",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders={"docs_url": DOCS_TROUBLESHOOTING_URL},
        )


async def _async_after_account_deleted(hass: HomeAssistant, email: str) -> None:
    """Leave a lasting note, and remove every entry of the deleted account.

    The removal is scheduled rather than awaited: the options flow that asked
    for it belongs to one of these entries and must finish first. A plain
    Home Assistant task is used on purpose -- a task owned by the entry would
    be cancelled by the very unload it performs.
    """
    strings = await async_get_translations(hass, hass.config.language, "exceptions", {DOMAIN})
    prefix = f"component.{DOMAIN}.exceptions"
    persistent_notification.async_create(
        hass,
        strings.get(
            f"{prefix}.account_deleted.message",
            "Your MeteoVeo account has been deleted, and the integration removed.",
        ),
        title=strings.get(f"{prefix}.account_deleted_title.message", "MeteoVeo"),
        notification_id=f"{DOMAIN}_account_deleted",
    )
    for other in hass.config_entries.async_entries(DOMAIN):
        if same_email(other.data.get(CONF_EMAIL), email):
            hass.async_create_task(
                hass.config_entries.async_remove(other.entry_id), eager_start=False
            )
