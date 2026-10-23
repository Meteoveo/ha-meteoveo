/*
 * MeteoVeo card for Home Assistant.
 *
 * One plain ES module, no build step, no imports: Home Assistant may run
 * offline and the integration serves this file itself. The element is a
 * vanilla custom element with a shadow root; `ha-card` and `ha-icon` come
 * from the HA frontend.
 *
 * Everything the card shows comes from the integration's entities — the
 * weather entity (current + forecasts over the websocket), the "rain soon"
 * binary sensor (the 10-minute steps of the next 3 hours), the warnings
 * sensor and, when the integration is new enough to have them, the feels-like,
 * dew point and UV sensors (sunrise/sunset come from HA's own `sun.sun`).
 * The card never talks to the network on its own.
 *
 * The pure helpers at the top (step model → sentence) are exported so they
 * can be unit-tested with `node --test`; the element is only defined when a
 * DOM exists.
 */

export const CARD_VERSION = "0.2.0";
const DOMAIN = "meteoveo";
const STEP_MINUTES = 10;
const HORIZON_MINUTES = 180;
/** Older than this the nowcast is not a statement about "now" any more. */
const STALE_MINUTES = 120;
/** From here on the age is shown in the warning colour. */
const AGEING_MINUTES = 45;

// ---------------------------------------------------------------------------
// Texts. Spanish is the product language; English is the fallback; Catalan
// mirrors the app's own strings.
// ---------------------------------------------------------------------------

const TEXT = {
  es: {
    nextHours: "Próximas 3 horas",
    hourly: "Por horas",
    daily: "Próximos días",
    now: "ahora",
    today: "hoy",
    tomorrow: "mañana",
    ago: "hace {n} min",
    radar: "radar",
    model: "modelo",
    dry: "Sin lluvia en las próximas 3 h",
    dryHour: "Sin lluvia la próxima hora",
    dryUncertain: "Probablemente sin lluvia · incierto a partir de ~{n} min",
    maybeNow: "Puede estar lloviendo ahora",
    rainNow: "Lluvia {band} ahora",
    ends: "Lluvia {band} hasta las {t}",
    throughout: "Lluvia {band} en las próximas 3 h",
    startsIn: "Lluvia {band} en ~{n} min",
    startsAt: "Lluvia {band} desde las {t}",
    maybeIn: "Podría llover en ~{n} min",
    noData: "Sin datos de precipitación ahora",
    stale: "Sin datos recientes del radar",
    uncertainLegend: "Punteado: incierto",
    band: { weak: "débil", moderate: "moderada", strong: "fuerte" },
    warning: { yellow: "Aviso amarillo", orange: "Aviso naranja", red: "Aviso rojo" },
    moreWarnings: "+{n} más",
    lessWarnings: "menos",
    until: "hasta las {t}", untilTomorrow: "hasta mañana a las {t}", untilDay: "hasta el {d} a las {t}",
    from: "desde las {t}", fromTomorrow: "desde mañana a las {t}", fromDay: "desde el {d} a las {t}",
    noEntity: "Añade la integración de MeteoVeo y elige su entidad weather.",
    unavailable: "Sin datos de MeteoVeo ahora mismo",
    humidity: "Humedad",
    wind: "Viento",
    feelsLike: "Sensación", feelsLikeLong: "Sensación térmica",
    dewPoint: "Rocío", dewPointLong: "Punto de rocío",
    uv: "UV", uvLong: "Índice UV", uvMax: "máx. {n}",
    uvLevel: { low: "bajo", moderate: "moderado", high: "alto", veryHigh: "muy alto", extreme: "extremo" },
    sunrise: "Salida del sol", sunset: "Puesta de sol",
    compass: ["N", "NE", "E", "SE", "S", "SO", "O", "NO"],
    condition: {
      "clear-night": "Despejado", cloudy: "Nublado", fog: "Niebla", hail: "Granizo",
      lightning: "Tormenta", "lightning-rainy": "Tormenta", partlycloudy: "Parcialmente nublado",
      pouring: "Lluvia intensa", rainy: "Lluvia", snowy: "Nieve", "snowy-rainy": "Aguanieve",
      sunny: "Soleado", windy: "Ventoso", "windy-variant": "Ventoso", exceptional: "Excepcional",
    },
    editor: {
      entity: "Entidad weather de MeteoVeo", rain_entity: "Sensor «Lluvia en la próxima hora» (opcional)",
      warnings_entity: "Sensor de avisos (opcional)", show_next_hour: "Próximas 3 horas",
      show_hourly: "Por horas", show_daily: "Próximos días", show_warnings: "Avisos AEMET",
      hourly_count: "Horas mostradas", daily_count: "Días mostrados",
      compact: "Modo compacto (ahora + próximas 3 horas)", show_details: "Detalles de ahora (sensación, UV, sol)",
      show_precipitation: "Lluvia por horas (mm)",
      compact_warnings: "Avisos en modo compacto",
      compact_warnings_options: { severe: "Solo naranja y rojo", all: "Todos los activos", none: "Ninguno" },
    },
  },
  en: {
    nextHours: "Next 3 hours",
    hourly: "Hourly",
    daily: "Next days",
    now: "now",
    today: "today",
    tomorrow: "tomorrow",
    ago: "{n} min ago",
    radar: "radar",
    model: "model",
    dry: "No rain in the next 3 h",
    dryHour: "No rain in the next hour",
    dryUncertain: "Probably no rain · uncertain from ~{n} min",
    maybeNow: "It may be raining now",
    rainNow: "Raining now ({band})",
    ends: "Rain until {t} ({band})",
    throughout: "Rain for the next 3 h ({band})",
    startsIn: "Rain in ~{n} min ({band})",
    startsAt: "Rain from {t} ({band})",
    maybeIn: "Rain possible in ~{n} min",
    noData: "No precipitation data right now",
    stale: "No recent radar data",
    uncertainLegend: "Dotted: uncertain",
    band: { weak: "light", moderate: "moderate", strong: "heavy" },
    warning: { yellow: "Yellow warning", orange: "Orange warning", red: "Red warning" },
    moreWarnings: "+{n} more",
    lessWarnings: "less",
    until: "until {t}", untilTomorrow: "until tomorrow {t}", untilDay: "until {d} {t}",
    from: "from {t}", fromTomorrow: "from tomorrow {t}", fromDay: "from {d} {t}",
    noEntity: "Add the MeteoVeo integration and pick its weather entity.",
    unavailable: "MeteoVeo data unavailable right now",
    humidity: "Humidity",
    wind: "Wind",
    feelsLike: "Feels like", feelsLikeLong: "Feels like",
    dewPoint: "Dew point", dewPointLong: "Dew point",
    uv: "UV", uvLong: "UV index", uvMax: "max {n}",
    uvLevel: { low: "low", moderate: "moderate", high: "high", veryHigh: "very high", extreme: "extreme" },
    sunrise: "Sunrise", sunset: "Sunset",
    compass: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    condition: {
      "clear-night": "Clear", cloudy: "Cloudy", fog: "Fog", hail: "Hail", lightning: "Thunderstorm",
      "lightning-rainy": "Thunderstorm", partlycloudy: "Partly cloudy", pouring: "Heavy rain",
      rainy: "Rain", snowy: "Snow", "snowy-rainy": "Sleet", sunny: "Sunny", windy: "Windy",
      "windy-variant": "Windy", exceptional: "Exceptional",
    },
    editor: {
      entity: "MeteoVeo weather entity", rain_entity: "“Rain soon” sensor (optional)",
      warnings_entity: "Warnings sensor (optional)", show_next_hour: "Next 3 hours",
      show_hourly: "Hourly", show_daily: "Next days", show_warnings: "AEMET warnings",
      hourly_count: "Hours shown", daily_count: "Days shown",
      compact: "Compact mode (now + next 3 hours)", show_details: "Now details (feels like, UV, sun)",
      show_precipitation: "Hourly rain (mm)",
      compact_warnings: "Warnings in compact mode",
      compact_warnings_options: { severe: "Orange and red only", all: "All active", none: "None" },
    },
  },
  ca: {
    nextHours: "Pròximes 3 hores",
    hourly: "Per hores",
    daily: "Pròxims dies",
    now: "ara",
    today: "avui",
    tomorrow: "demà",
    ago: "fa {n} min",
    radar: "radar",
    model: "model",
    dry: "Sense pluja en les pròximes 3 h",
    dryHour: "Sense pluja la pròxima hora",
    dryUncertain: "Probablement sense pluja · incert a partir de ~{n} min",
    maybeNow: "Pot estar plovent ara",
    rainNow: "Pluja {band} ara",
    ends: "Pluja {band} fins a les {t}",
    throughout: "Pluja {band} en les pròximes 3 h",
    startsIn: "Pluja {band} d’aquí a ~{n} min",
    startsAt: "Pluja {band} des de les {t}",
    maybeIn: "Podria ploure d’aquí a ~{n} min",
    noData: "Sense dades de precipitació ara",
    stale: "Sense dades recents del radar",
    uncertainLegend: "Puntejat: incert",
    band: { weak: "feble", moderate: "moderada", strong: "forta" },
    warning: { yellow: "Avís groc", orange: "Avís taronja", red: "Avís vermell" },
    moreWarnings: "+{n} més",
    lessWarnings: "menys",
    until: "fins a les {t}", untilTomorrow: "fins demà a les {t}", untilDay: "fins {d} a les {t}",
    from: "des de les {t}", fromTomorrow: "des de demà a les {t}", fromDay: "des de {d} a les {t}",
    noEntity: "Afegeix la integració de MeteoVeo i tria la seva entitat weather.",
    unavailable: "Sense dades de MeteoVeo ara mateix",
    humidity: "Humitat",
    wind: "Vent",
    feelsLike: "Sensació", feelsLikeLong: "Sensació tèrmica",
    dewPoint: "Rosada", dewPointLong: "Punt de rosada",
    uv: "UV", uvLong: "Índex UV", uvMax: "màx. {n}",
    uvLevel: { low: "baix", moderate: "moderat", high: "alt", veryHigh: "molt alt", extreme: "extrem" },
    sunrise: "Sortida del sol", sunset: "Posta de sol",
    compass: ["N", "NE", "E", "SE", "S", "SO", "O", "NO"],
    condition: {
      "clear-night": "Serè", cloudy: "Ennuvolat", fog: "Boira", hail: "Calamarsa", lightning: "Tempesta",
      "lightning-rainy": "Tempesta", partlycloudy: "Parcialment ennuvolat", pouring: "Pluja intensa",
      rainy: "Pluja", snowy: "Neu", "snowy-rainy": "Aiguaneu", sunny: "Assolellat", windy: "Ventós",
      "windy-variant": "Ventós", exceptional: "Excepcional",
    },
    editor: {
      entity: "Entitat weather de MeteoVeo", rain_entity: "Sensor «Pluja en la pròxima hora» (opcional)",
      warnings_entity: "Sensor d’avisos (opcional)", show_next_hour: "Pròximes 3 hores",
      show_hourly: "Per hores", show_daily: "Pròxims dies", show_warnings: "Avisos AEMET",
      hourly_count: "Hores mostrades", daily_count: "Dies mostrats",
      compact: "Mode compacte (ara + pròximes 3 hores)", show_details: "Detalls d’ara (sensació, UV, sol)",
      show_precipitation: "Pluja per hores (mm)",
      compact_warnings: "Avisos en mode compacte",
      compact_warnings_options: { severe: "Només taronja i vermell", all: "Tots els actius", none: "Cap" },
    },
  },
  // Hungarian: for the owner's review, not a product language.
  hu: {
    nextHours: "Következő 3 óra",
    hourly: "Óránként",
    daily: "Következő napok",
    now: "most",
    today: "ma",
    tomorrow: "holnap",
    ago: "{n} perce",
    radar: "radar",
    model: "modell",
    dry: "Nem esik a következő 3 órában",
    dryHour: "Nem esik a következő órában",
    dryUncertain: "Valószínűleg nem esik · bizonytalan ~{n} perctől",
    maybeNow: "Lehet, hogy most esik",
    rainNow: "Most esik ({band})",
    ends: "Eső {t}-ig ({band})",
    throughout: "Eső a következő 3 órában ({band})",
    startsIn: "Eső ~{n} perc múlva ({band})",
    startsAt: "Eső {t}-tól ({band})",
    maybeIn: "~{n} perc múlva eshet",
    noData: "Most nincs csapadékadat",
    stale: "Nincs friss radaradat",
    uncertainLegend: "Pontozott: bizonytalan",
    band: { weak: "gyenge", moderate: "mérsékelt", strong: "erős" },
    warning: { yellow: "Sárga figyelmeztetés", orange: "Narancs figyelmeztetés", red: "Piros figyelmeztetés" },
    moreWarnings: "+{n} további",
    lessWarnings: "kevesebb",
    until: "{t}-ig", untilTomorrow: "holnap {t}-ig", untilDay: "{d} {t}-ig",
    from: "{t}-tól", fromTomorrow: "holnap {t}-tól", fromDay: "{d} {t}-tól",
    noEntity: "Add hozzá a MeteoVeo-integrációt, és válaszd ki a weather entitását.",
    unavailable: "Most nincs MeteoVeo-adat",
    humidity: "Páratartalom",
    wind: "Szél",
    feelsLike: "Hőérzet", feelsLikeLong: "Hőérzet",
    dewPoint: "Harmatpont", dewPointLong: "Harmatpont",
    uv: "UV", uvLong: "UV-index", uvMax: "max. {n}",
    uvLevel: { low: "alacsony", moderate: "mérsékelt", high: "magas", veryHigh: "nagyon magas", extreme: "extrém" },
    sunrise: "Napkelte", sunset: "Napnyugta",
    compass: ["É", "ÉK", "K", "DK", "D", "DNy", "Ny", "ÉNy"],
    condition: {
      "clear-night": "Derült", cloudy: "Borult", fog: "Köd", hail: "Jégeső", lightning: "Zivatar",
      "lightning-rainy": "Zivatar", partlycloudy: "Részben felhős", pouring: "Heves eső",
      rainy: "Eső", snowy: "Havazás", "snowy-rainy": "Havas eső", sunny: "Napos", windy: "Szeles",
      "windy-variant": "Szeles", exceptional: "Rendkívüli",
    },
    editor: {
      entity: "MeteoVeo weather entitás", rain_entity: "„Eső a következő órában” szenzor (nem kötelező)",
      warnings_entity: "Figyelmeztetés-szenzor (nem kötelező)", show_next_hour: "Következő 3 óra",
      show_hourly: "Óránként", show_daily: "Következő napok", show_warnings: "AEMET-figyelmeztetések",
      hourly_count: "Mutatott órák", daily_count: "Mutatott napok",
      compact: "Kompakt mód (most + következő 3 óra)", show_details: "A „most” részletei (hőérzet, UV, nap)",
      show_precipitation: "Órás csapadék (mm)",
      compact_warnings: "Figyelmeztetések kompakt módban",
      compact_warnings_options: { severe: "Csak narancs és piros", all: "Minden aktív", none: "Egyik sem" },
    },
  },
};

export function pickLanguage(hassLanguage) {
  const code = String(hassLanguage || "en").toLowerCase().split(/[-_]/)[0];
  return TEXT[code] ? code : "en";
}

function fill(template, vars) {
  return String(template).replace(/\{(\w+)\}/g, (_, k) => (vars && k in vars ? vars[k] : `{${k}}`));
}

// ---------------------------------------------------------------------------
// Next-hour model: the binary sensor's `steps` → what to draw and what to say.
// Pure; `nowMs` is injected for tests.
// ---------------------------------------------------------------------------

const BAND_ALIAS = { none: "none", light: "weak", weak: "weak", moderate: "moderate", heavy: "strong", strong: "strong" };
const BAND_RANK = { weak: 1, moderate: 2, strong: 3 };
/** Bar height as a fraction of the strip — the band's mid value on the app's mm scale (0.2–1 / 1–5 / 5+). */
export const BAND_FRACTION = { weak: 0.3, moderate: 0.6, strong: 1 };

function normalizeStep(raw) {
  const lead = Number(raw && raw.lead_minutes);
  if (!Number.isFinite(lead)) return null;
  const band = raw.band in BAND_ALIAS ? BAND_ALIAS[raw.band] : null;
  return { lead, band, uncertain: raw.uncertain === true, source: raw.source || null, at: raw.at || null };
}

function strongest(segment) {
  return segment.reduce((best, s) => (BAND_RANK[s.band] > (BAND_RANK[best] || 0) ? s.band : best), null);
}

/**
 * @param {object|null} attrs  the binary sensor's attributes
 * @param {number} nowMs
 * @returns {null | {kind, band, minutes, atMs, ageMinutes, source, slots}}
 *   kind: dry | dry-hour | dry-uncertain | maybe-now | rain-now | ends | throughout |
 *         starts | maybe | no-data | stale
 */
export function nextHourModel(attrs, nowMs) {
  if (!attrs || !Array.isArray(attrs.steps)) return null;
  const steps = attrs.steps.map(normalizeStep).filter(Boolean).sort((a, b) => a.lead - b.lead);
  if (steps.length === 0) return null;

  // The age is counted live from issued_at: a reply reused after a 304 carries an
  // age_minutes that was only true when it was sent. age_minutes is the fallback.
  const issued = Date.parse(attrs.issued_at || "");
  let age = Number.isFinite(issued) ? Math.max(0, (nowMs - issued) / 60000) : Number(attrs.age_minutes);
  if (!Number.isFinite(age)) age = 0;
  const source = steps.find((s) => s.source)?.source || null;

  // Steps that already began are the past; the one containing "now" is the first slot.
  // The leads count from the first step's own time (when the reply was computed),
  // not from the nowcast run, so that is what the elapsed time is measured from.
  const firstAt = Date.parse(steps[0].at || "");
  const elapsed = Number.isFinite(firstAt) ? Math.max(0, (nowMs - firstAt) / 60000) : age;
  const shift = Math.floor(elapsed / STEP_MINUTES) * STEP_MINUTES;
  const slots = steps
    .filter((s) => s.lead >= shift && s.lead - shift <= HORIZON_MINUTES)
    .map((s) => ({ ...s, minutes: s.lead - shift }));
  const base = { ageMinutes: Math.round(age), source, slots, band: null, minutes: 0, atMs: null };

  if (age > STALE_MINUTES) return { ...base, kind: "stale" };
  if (slots.length === 0 || slots[0].band === null) return { ...base, kind: "no-data" };

  const atOf = (s) => {
    const t = Date.parse(s.at || "");
    return Number.isFinite(t) ? t : null;
  };
  const now = slots[0];
  const wet = (s) => s.band !== null && s.band !== "none";

  if (wet(now)) {
    if (now.uncertain) return { ...base, kind: "maybe-now" };
    const segment = [];
    for (const s of slots) {
      if (!wet(s)) break;
      segment.push(s);
    }
    const band = strongest(segment);
    const next = slots[segment.length];
    if (!next) return { ...base, kind: "throughout", band };
    if (next.band === "none") return { ...base, kind: "ends", band, minutes: next.minutes, atMs: atOf(next) };
    return { ...base, kind: "rain-now", band };
  }

  const firstWet = slots.find(wet);
  if (firstWet) {
    if (firstWet.uncertain) return { ...base, kind: "maybe", minutes: firstWet.minutes, atMs: atOf(firstWet) };
    const segment = [];
    for (const s of slots.slice(slots.indexOf(firstWet))) {
      if (!wet(s)) break;
      segment.push(s);
    }
    return { ...base, kind: "starts", band: strongest(segment), minutes: firstWet.minutes, atMs: atOf(firstWet) };
  }

  const firstUncertain = slots.find((s) => s.minutes > 0 && s.uncertain);
  if (firstUncertain) return { ...base, kind: "dry-uncertain", minutes: firstUncertain.minutes };
  const known = slots.filter((s) => s.band !== null);
  const covered = known.length ? known[known.length - 1].minutes : 0;
  if (covered >= HORIZON_MINUTES - STEP_MINUTES) return { ...base, kind: "dry" };
  if (covered >= 60) return { ...base, kind: "dry-hour" };
  return { ...base, kind: "no-data" };
}

/** The one-line sentence for a model. `clock(ms)` formats a time of day. */
export function nextHourSentence(model, lang, clock) {
  const t = TEXT[lang] || TEXT.en;
  if (!model) return t.noData;
  const band = model.band ? t.band[model.band] : "";
  const time = model.atMs !== null && clock ? clock(model.atMs) : null;
  switch (model.kind) {
    case "dry": return t.dry;
    case "dry-hour": return t.dryHour;
    case "dry-uncertain": return fill(t.dryUncertain, { n: model.minutes });
    case "maybe-now": return t.maybeNow;
    case "rain-now": return fill(t.rainNow, { band });
    case "throughout": return fill(t.throughout, { band });
    case "ends": return time ? fill(t.ends, { band, t: time }) : fill(t.rainNow, { band });
    case "maybe": return fill(t.maybeIn, { n: model.minutes });
    case "starts":
      return model.minutes <= 90 || !time ? fill(t.startsIn, { band, n: model.minutes }) : fill(t.startsAt, { band, t: time });
    case "stale": return t.stale;
    default: return t.noData;
  }
}

// ---------------------------------------------------------------------------
// Small formatting helpers.
// ---------------------------------------------------------------------------

export function compassPoint(bearing, lang) {
  const b = Number(bearing);
  if (!Number.isFinite(b)) return "";
  const points = (TEXT[lang] || TEXT.en).compass;
  return points[Math.round((((b % 360) + 360) % 360) / 45) % 8];
}

const ICON = {
  "clear-night": "mdi:weather-night", cloudy: "mdi:weather-cloudy", fog: "mdi:weather-fog",
  hail: "mdi:weather-hail", lightning: "mdi:weather-lightning", "lightning-rainy": "mdi:weather-lightning-rainy",
  partlycloudy: "mdi:weather-partly-cloudy", pouring: "mdi:weather-pouring", rainy: "mdi:weather-rainy",
  snowy: "mdi:weather-snowy", "snowy-rainy": "mdi:weather-snowy-rainy", sunny: "mdi:weather-sunny",
  windy: "mdi:weather-windy", "windy-variant": "mdi:weather-windy-variant", exceptional: "mdi:alert-circle-outline",
};
const NIGHT_ICON = { sunny: "mdi:weather-night", partlycloudy: "mdi:weather-night-partly-cloudy" };

export function conditionIcon(condition, isDay) {
  if (isDay === false && NIGHT_ICON[condition]) return NIGHT_ICON[condition];
  return ICON[condition] || "mdi:weather-cloudy";
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const WARN_COLOR = { yellow: "#f2c200", orange: "#ef6c00", red: "#f2003c" };
const WARN_RANK = { none: 0, yellow: 1, orange: 2, red: 3 };

/** The WHO UV index scale and its colours. */
const UV_LEVELS = [
  [2, "low", "#3ea72d"], [5, "moderate", "#f7d117"], [7, "high", "#f18b00"], [10, "veryHigh", "#e53210"], [Infinity, "extreme", "#b567a4"],
];
export function uvLevel(value) {
  const n = Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(n) || n < 0) return null;
  const [, key, color] = UV_LEVELS.find(([max]) => Math.round(n) <= max);
  return { key, color };
}

/** An hourly amount on the app's mm scale: 0.2–1 weak, 1–5 moderate, 5+ strong. */
export function precipBand(mm) {
  const n = Number(mm);
  if (mm === null || mm === undefined || mm === "" || !Number.isFinite(n) || n < 0.1) return null;
  return n < 1 ? "weak" : n < 5 ? "moderate" : "strong";
}

/**
 * The warnings sensor's list → what to show, in order: the active ones (highest
 * level first, the one ending soonest first among equals), then the upcoming
 * ones by onset. Expired entries are dropped; one without dates counts as active.
 */
export function warningSchedule(list, nowMs) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const w of list) {
    if (!w || typeof w !== "object") continue;
    const onset = Date.parse(w.onset || "");
    const expires = Date.parse(w.expires || "");
    if (Number.isFinite(expires) && expires <= nowMs) continue;
    const phase = Number.isFinite(onset) && onset > nowMs ? "upcoming" : "active";
    const level = WARN_COLOR[w.level] ? w.level : "yellow";
    out.push({ ...w, level, phase, onsetMs: Number.isFinite(onset) ? onset : null, expiresMs: Number.isFinite(expires) ? expires : null });
  }
  const far = Number.MAX_SAFE_INTEGER;
  return out.sort((a, b) => {
    if (a.phase !== b.phase) return a.phase === "active" ? -1 : 1;
    if (a.phase === "upcoming" && a.onsetMs !== b.onsetMs) return (a.onsetMs ?? far) - (b.onsetMs ?? far);
    if (WARN_RANK[a.level] !== WARN_RANK[b.level]) return WARN_RANK[b.level] - WARN_RANK[a.level];
    return (a.expiresMs ?? far) - (b.expiresMs ?? far);
  });
}

/**
 * "hasta las 21:00" / "desde mañana a las 06:00". `rel` is "today", "tomorrow"
 * or an already formatted day ("sáb 25"); `time` the formatted clock.
 */
export function validityText(phase, rel, time, lang) {
  const t = TEXT[lang] || TEXT.en;
  if (!time) return "";
  const key = phase === "upcoming" ? "from" : "until";
  if (rel === "today") return fill(t[key], { t: time });
  if (rel === "tomorrow") return fill(t[`${key}Tomorrow`], { t: time });
  return fill(t[`${key}Day`], { d: rel, t: time });
}

/** How many warnings are shown before the "+N more" fold. */
const WARNINGS_FOLD = 2;

/**
 * Which warnings the compact card keeps (owner, 2026-10-23: configurable):
 * "severe" = active orange and red (the default), "all" = every active one,
 * "none" = nothing. Upcoming warnings never show in compact mode.
 */
export function compactWarnings(schedule, mode) {
  if (mode === "none") return [];
  return schedule.filter(
    (w) => w.phase === "active" && (mode === "all" || w.level === "orange" || w.level === "red"),
  );
}

// ---------------------------------------------------------------------------
// Styles. HA theme variables carry the surface and the type; the MeteoVeo
// accents (the rain blue, amber, terracotta, green) come from the app's palette
// and get their dark-mode values from `data-dark`.
// ---------------------------------------------------------------------------

const STYLE = `
:host { display: block;
  --mv-blue: #2f92c6; --mv-blue-soft: #7fb6cf; --mv-blue-deep: #1b5f8c; --mv-green: #2f7d63;
  --mv-amber: #f4a935; --mv-terracotta: #bd4a2b; --mv-warn-ink: #8a5417;
  --mv-ink: var(--primary-text-color, #12302b); --mv-ink-2: var(--secondary-text-color, #5c7168);
  --mv-line: var(--divider-color, rgba(40,90,78,.16)); --mv-line-strong: rgba(127,182,207,.45);
  --mv-track: rgba(127,182,207,.18); }
:host([data-dark]) { --mv-blue: #56aede; --mv-blue-soft: #7fb6cf; --mv-blue-deep: #2f92c6; --mv-green: #4aa583;
  --mv-amber: #f0b756; --mv-terracotta: #dd6a48; --mv-warn-ink: #e8b57a;
  --mv-line-strong: rgba(127,182,207,.35); --mv-track: rgba(127,182,207,.14); }
ha-card { overflow: hidden; }
.mv { padding: 16px; color: var(--mv-ink); font-variant-numeric: tabular-nums; }
.mv * { box-sizing: border-box; }
.label { font-size: 10px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--mv-ink-2); }
.label-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.place { font-size: 15px; font-weight: 600; line-height: 1.25; overflow-wrap: anywhere; }
.temp-row { display: flex; align-items: baseline; gap: 10px; margin-top: 2px; flex-wrap: wrap; }
.temp { font-size: 44px; font-weight: 300; line-height: 1; letter-spacing: -.02em; }
.cond { font-size: 14px; color: var(--mv-ink-2); }
.meta { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; font-size: 13px; color: var(--mv-ink-2); }
.meta span { display: inline-flex; align-items: center; gap: 3px; }
.meta ha-icon { --mdc-icon-size: 16px; color: var(--mv-ink-2); }
.meta b { font-weight: 500; color: var(--mv-ink); }
.hero-icon { --mdc-icon-size: 52px; flex: none; color: var(--mv-ink); margin-top: 2px; }
.details { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 10px; font-size: 13px; color: var(--mv-ink-2); }
.details span { display: inline-flex; align-items: center; gap: 4px; }
.details ha-icon { --mdc-icon-size: 16px; color: var(--mv-ink-2); }
.details b { font-weight: 500; color: var(--mv-ink); }
.details .uv-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; margin-left: 1px; box-shadow: inset 0 0 0 1px rgba(0,0,0,.12); }
.details .uv-max { font-size: 11.5px; }
section { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--mv-line); }
.sentence { margin: 0; font-size: 15px; font-weight: 500; line-height: 1.3; }
.sentence.soft { font-weight: 400; color: var(--mv-ink-2); }
.age { font-size: 11px; color: var(--mv-ink-2); white-space: nowrap; }
.age.old { color: var(--mv-warn-ink); font-weight: 500; }
.strip { display: flex; align-items: flex-end; gap: 2px; height: 36px; margin-top: 10px; }
.slot { flex: 1 1 0; min-width: 2px; height: 3px; border-radius: 2px; background: var(--mv-line-strong); }
.slot.weak { background: var(--mv-blue-soft); }
.slot.moderate { background: var(--mv-blue); }
.slot.strong { background: var(--mv-blue-deep); }
.slot.unknown { background: transparent; border-bottom: 1px dashed var(--mv-line-strong); border-radius: 0; }
.slot.uncertain { opacity: .75; background-image: repeating-linear-gradient(135deg, transparent 0 2px, rgba(255,255,255,.55) 2px 4px); }
:host([data-dark]) .slot.uncertain { background-image: repeating-linear-gradient(135deg, transparent 0 2px, rgba(0,0,0,.45) 2px 4px); }
.stale .slot { opacity: .35; }
.axis { display: flex; justify-content: space-between; margin-top: 5px; font-size: 11px; color: var(--mv-ink-2); }
.legend { margin-top: 6px; font-size: 10.5px; color: var(--mv-ink-2); opacity: .8; }
.warn { display: flex; gap: 10px; align-items: flex-start; margin-top: 14px; padding: 10px 12px; border-radius: 10px;
  border-left: 4px solid var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); }
.warn + .warn { margin-top: 8px; }
.warn.upcoming { background: color-mix(in srgb, var(--warn) 6%, transparent); border-left-style: dashed; }
.warn ha-icon { --mdc-icon-size: 22px; color: var(--warn); flex: none; }
.warn-body { flex: 1 1 auto; min-width: 0; }
.warn-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.warn-title { font-size: 14px; font-weight: 600; }
.warn-when { font-size: 12px; font-weight: 500; color: var(--mv-ink-2); white-space: nowrap; }
.warn-text { font-size: 12.5px; color: var(--mv-ink-2); margin-top: 2px; line-height: 1.35; }
.more { display: block; margin: 6px 0 0; padding: 4px 0; border: 0; background: none; font: inherit; font-size: 12.5px; font-weight: 500;
  color: var(--mv-blue); cursor: pointer; }
.more:focus-visible { outline: 2px solid var(--mv-blue); outline-offset: 2px; border-radius: 4px; }
.hour .mm { font-size: 10.5px; font-weight: 500; color: var(--mv-blue); min-height: 1.2em; }
.pbar { display: flex; align-items: flex-end; justify-content: center; width: 100%; height: 18px; padding: 0 14px; }
.pbar i { display: block; width: 100%; border-radius: 2px 2px 0 0; background: var(--mv-line-strong); }
.pbar i.weak { background: var(--mv-blue-soft); }
.pbar i.moderate { background: var(--mv-blue); }
.pbar i.strong { background: var(--mv-blue-deep); }
.pbar i.none { height: 2px; background: var(--mv-track); }
.scroll { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; margin: 0 -16px; padding: 0 16px; }
.scroll::-webkit-scrollbar { display: none; }
.hour { flex: 0 0 52px; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px 0; }
.hour .h { font-size: 12px; font-weight: 500; color: var(--mv-ink-2); }
.hour ha-icon { --mdc-icon-size: 24px; }
.hour .t { font-size: 15px; font-weight: 600; }
.hour .p { font-size: 11px; font-weight: 500; color: var(--mv-blue); min-height: 1.2em; }
.day { display: grid; grid-template-columns: minmax(3.4em, max-content) 28px 3em 2.6em minmax(40px, 1fr) 2.6em; align-items: center;
  gap: 8px; padding: 7px 0; border-bottom: 1px solid var(--mv-line); font-size: 14px; }
.day:last-child { border-bottom: 0; }
.day .d { font-weight: 500; text-transform: capitalize; white-space: nowrap; }
.day ha-icon { --mdc-icon-size: 24px; }
.day .p { font-size: 12px; font-weight: 500; color: var(--mv-blue); }
.day .lo { color: var(--mv-ink-2); text-align: right; }
.day .hi { font-weight: 600; text-align: left; }
.bar { position: relative; height: 5px; border-radius: 3px; background: var(--mv-track); }
.bar i { position: absolute; top: 0; bottom: 0; border-radius: 3px;
  background: linear-gradient(90deg, var(--mv-blue-soft), var(--mv-amber)); }
.empty { padding: 4px 0; font-size: 14px; color: var(--mv-ink-2); line-height: 1.4; }
.attr { margin-top: 12px; font-size: 10.5px; color: var(--mv-ink-2); opacity: .75; }
`;

// ---------------------------------------------------------------------------
// The element.
// ---------------------------------------------------------------------------

const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

export class MeteoVeoCard extends Base {
  static getStubConfig(hass, entities) {
    const all = hass && hass.entities ? Object.values(hass.entities) : [];
    const ours = all.find((e) => e.platform === DOMAIN && e.entity_id.startsWith("weather."));
    const fallback = (entities || []).find((id) => id.startsWith("weather."));
    return { entity: ours ? ours.entity_id : fallback || "" };
  }

  static getConfigForm() {
    const lang = () => MeteoVeoCard._lang || "en";
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "weather", integration: DOMAIN } } },
        { name: "rain_entity", selector: { entity: { domain: "binary_sensor", integration: DOMAIN } } },
        { name: "warnings_entity", selector: { entity: { domain: "sensor", integration: DOMAIN } } },
        {
          type: "grid", name: "",
          schema: [
            { name: "show_next_hour", default: true, selector: { boolean: {} } },
            { name: "show_warnings", default: true, selector: { boolean: {} } },
            { name: "show_hourly", default: true, selector: { boolean: {} } },
            { name: "show_daily", default: true, selector: { boolean: {} } },
            { name: "show_details", default: true, selector: { boolean: {} } },
            { name: "show_precipitation", default: true, selector: { boolean: {} } },
          ],
        },
        { name: "compact", default: false, selector: { boolean: {} } },
        {
          name: "compact_warnings",
          default: "severe",
          selector: {
            select: {
              mode: "dropdown",
              options: ["severe", "all", "none"].map((value) => ({
                value,
                label: TEXT[lang()].editor.compact_warnings_options[value],
              })),
            },
          },
        },
        {
          type: "grid", name: "",
          schema: [
            { name: "hourly_count", default: 12, selector: { number: { min: 3, max: 48, mode: "box" } } },
            { name: "daily_count", default: 7, selector: { number: { min: 1, max: 14, mode: "box" } } },
          ],
        },
      ],
      computeLabel: (schema) => TEXT[lang()].editor[schema.name] || schema.name,
      assertConfig: (config) => {
        if (!config.entity || !String(config.entity).startsWith("weather.")) throw new Error("entity must be a weather entity");
      },
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._lang = "en";
    this._forecast = { hourly: null, daily: null };
    this._subs = [];
    this._subscribedTo = null;
    this._snapshot = null;
    this._connected = false;
    this._warningsExpanded = false;
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("MeteoVeo: set `entity` to the MeteoVeo weather entity");
    this._config = {
      show_next_hour: true, show_hourly: true, show_daily: true, show_warnings: true,
      show_details: true, show_precipitation: true, compact: false, compact_warnings: "severe",
      hourly_count: 12, daily_count: 7, ...config,
    };
    this._snapshot = null;
    this._warningsExpanded = false;
    this._resubscribe();
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._lang = pickLanguage(hass && hass.locale && hass.locale.language);
    MeteoVeoCard._lang = this._lang;
    if (!this._config) return;
    this._resubscribe();
    // Re-render only when something the card shows has changed.
    const ids = this._entityIds();
    const watched = [ids.weather, ids.rain, ids.warnings, ids.apparent, ids.dewPoint, ids.uv, ids.uvMax, "sun.sun"];
    const snap = [
      ...watched, this._lang,
      hass.themes && hass.themes.darkMode, hass.locale && hass.locale.time_format,
      ...watched.map((id) => (id && hass.states[id]) || null),
    ];
    if (this._snapshot && snap.every((v, i) => v === this._snapshot[i])) return;
    this._snapshot = snap;
    this._render();
  }

  get hass() { return this._hass; }

  connectedCallback() {
    this._connected = true;
    this._resubscribe();
  }

  disconnectedCallback() {
    this._connected = false;
    this._unsubscribe();
  }

  getCardSize() {
    const c = this._config || {};
    if (c.compact) return 2 + (c.show_next_hour ? 2 : 0);
    return 2 + (c.show_next_hour ? 2 : 0) + (c.show_hourly ? 2 : 0) + (c.show_daily ? Math.ceil((c.daily_count || 7) / 2) : 0);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // --- entities --------------------------------------------------------------

  _entityIds() {
    const c = this._config;
    const weather = c.entity;
    return {
      weather,
      rain: c.rain_entity || this._sibling(weather, "rain_soon", "binary_sensor."),
      warnings: c.warnings_entity || this._sibling(weather, "warnings", "sensor."),
      // 0.2.0 sensors; an older integration simply has none of them.
      apparent: this._sibling(weather, "apparent_temperature", "sensor."),
      dewPoint: this._sibling(weather, "dew_point", "sensor."),
      uv: this._sibling(weather, "uv_index", "sensor."),
      uvMax: this._sibling(weather, "uv_index_max_today", "sensor."),
    };
  }

  /** A sensor's numeric state, or null when it is missing, unavailable or not a number. */
  _sensorNumber(id) {
    const s = id && this._hass && this._hass.states[id];
    if (!s || s.state === "unavailable" || s.state === "unknown" || s.state === "") return null;
    const n = Number(s.state);
    return Number.isFinite(n) ? n : null;
  }

  /** A sibling entity of the same device, found by the integration's fixed translation key. */
  _sibling(weatherId, translationKey, prefix) {
    const reg = this._hass && this._hass.entities;
    if (!reg || !reg[weatherId]) return null;
    const deviceId = reg[weatherId].device_id;
    if (!deviceId) return null;
    const hit = Object.values(reg).find(
      (e) => e.device_id === deviceId && e.platform === DOMAIN && e.translation_key === translationKey && e.entity_id.startsWith(prefix),
    );
    return hit ? hit.entity_id : null;
  }

  // --- forecasts over the websocket ---------------------------------------------

  _resubscribe() {
    const hass = this._hass;
    if (!this._connected || !hass || !this._config || !hass.connection) return;
    const id = this._config.entity;
    if (this._subscribedTo === id) return;
    this._unsubscribe();
    this._subscribedTo = id;
    for (const type of ["hourly", "daily"]) {
      const p = hass.connection
        .subscribeMessage(
          (msg) => {
            if (this._subscribedTo !== id) return;
            this._forecast[type] = Array.isArray(msg && msg.forecast) ? msg.forecast : [];
            this._render();
          },
          { type: "weather/subscribe_forecast", forecast_type: type, entity_id: id },
        )
        .catch(() => {
          this._forecast[type] = [];
          this._render();
          return null;
        });
      this._subs.push(p);
    }
  }

  _unsubscribe() {
    const subs = this._subs;
    this._subs = [];
    this._subscribedTo = null;
    this._forecast = { hourly: null, daily: null };
    for (const p of subs) p.then((unsub) => typeof unsub === "function" && unsub()).catch(() => {});
  }

  // --- formatting ---------------------------------------------------------------

  _locale() {
    const l = this._hass && this._hass.locale;
    return (l && l.language) || "en";
  }

  _timeZone() {
    const c = this._hass && this._hass.config;
    return (c && c.time_zone) || undefined;
  }

  _clock(ms) {
    const tf = this._hass && this._hass.locale && this._hass.locale.time_format;
    const opts = { hour: "2-digit", minute: "2-digit", timeZone: this._timeZone() };
    if (tf === "12") opts.hour12 = true;
    if (tf === "24") opts.hour12 = false;
    try { return new Intl.DateTimeFormat(this._locale(), opts).format(new Date(ms)); } catch (e) { return ""; }
  }

  _hourLabel(ms) {
    try { return new Intl.DateTimeFormat(this._locale(), { hour: "numeric", timeZone: this._timeZone() }).format(new Date(ms)); } catch (e) { return ""; }
  }

  /** "today", "tomorrow", or the short weekday and day ("sáb 25") in the user's locale. */
  _relDay(ms, nowMs) {
    const tz = this._timeZone();
    const dayKey = (x) => { try { return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(x)); } catch (e) { return new Date(x).toDateString(); } };
    const k = dayKey(ms);
    if (k === dayKey(nowMs)) return "today";
    if (k === dayKey(nowMs + 86400000)) return "tomorrow";
    try {
      const d = new Date(ms);
      // Intl gives "25 Sun" and "25., V" without a month; English and Hungarian put the weekday first.
      if (this._lang === "hu" || this._lang === "en") {
        const wd = new Intl.DateTimeFormat(this._locale(), { weekday: "short", timeZone: tz }).format(d);
        const day = new Intl.DateTimeFormat(this._locale(), { day: "numeric", timeZone: tz }).format(d);
        return `${wd} ${day}${this._lang === "hu" ? "." : ""}`;
      }
      return new Intl.DateTimeFormat(this._locale(), { weekday: "short", day: "numeric", timeZone: tz }).format(d);
    } catch (e) { return k; }
  }

  _dayLabel(ms, nowMs) {
    const t = TEXT[this._lang];
    const rel = this._relDay(ms, nowMs);
    return rel === "today" ? t.today : rel === "tomorrow" ? t.tomorrow : rel;
  }

  _num(value, digits = 0) {
    // `Number(null)` is 0 — a missing value must never print as zero.
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    try { return new Intl.NumberFormat(this._locale(), { maximumFractionDigits: digits }).format(n); } catch (e) { return String(n); }
  }

  _deg(value) {
    const s = this._num(value, 0);
    return s === null ? "–" : `${s}°`;
  }

  // --- render -------------------------------------------------------------------

  _render() {
    if (!this.shadowRoot) return;
    let body;
    try {
      body = this._body();
    } catch (e) {
      body = `<div class="mv"><div class="empty">MeteoVeo: ${esc(e && e.message)}</div></div>`;
    }
    const dark = !!(this._hass && this._hass.themes && this._hass.themes.darkMode);
    if (dark) this.setAttribute("data-dark", ""); else this.removeAttribute("data-dark");
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${body}</ha-card>`;
    const more = this.shadowRoot.querySelector && this.shadowRoot.querySelector(".more");
    if (more) more.addEventListener("click", () => { this._warningsExpanded = !this._warningsExpanded; this._render(); });
  }

  _body() {
    const t = TEXT[this._lang];
    const hass = this._hass;
    if (!hass || !this._config) return `<div class="mv"><div class="empty">${esc(t.noEntity)}</div></div>`;
    const ids = this._entityIds();
    const weather = hass.states[ids.weather];
    if (!weather) return `<div class="mv"><div class="empty">${esc(t.noEntity)}</div></div>`;
    const nowMs = Date.now();
    const c = this._config;
    const parts = [this._hero(weather, nowMs)];
    if (weather.state === "unavailable" || weather.state === "unknown") {
      parts.push(`<div class="empty">${esc(t.unavailable)}</div>`);
    } else if (c.compact) {
      // Compact: the "now" header and the next 3 hours, plus the warnings the
      // `compact_warnings` option keeps (by default an active orange or red one).
      if (c.show_next_hour) parts.push(this._nextHour(ids.rain ? hass.states[ids.rain] : null, nowMs));
      if (c.show_warnings && c.compact_warnings !== "none") {
        parts.push(this._warnings(ids.warnings ? hass.states[ids.warnings] : null, nowMs, c.compact_warnings));
      }
    } else {
      if (c.show_details) parts.push(this._details(weather, ids));
      if (c.show_next_hour) parts.push(this._nextHour(ids.rain ? hass.states[ids.rain] : null, nowMs));
      if (c.show_warnings) parts.push(this._warnings(ids.warnings ? hass.states[ids.warnings] : null, nowMs));
      if (c.show_hourly) parts.push(this._hourly(weather, nowMs));
      if (c.show_daily) parts.push(this._daily(weather, nowMs));
    }
    const attribution = weather.attributes.attribution;
    if (attribution) parts.push(`<div class="attr">${esc(attribution)}</div>`);
    return `<div class="mv">${parts.join("")}</div>`;
  }

  _isDay(weather) {
    const h = this._forecast.hourly;
    if (h && h[0] && typeof h[0].is_daytime === "boolean") return h[0].is_daytime;
    const sun = this._hass.states["sun.sun"];
    if (sun) return sun.state !== "below_horizon";
    return weather.state !== "clear-night";
  }

  _hero(weather, nowMs) {
    const t = TEXT[this._lang];
    const a = weather.attributes;
    const name = this._config.name || a.friendly_name || "";
    const unavailable = weather.state === "unavailable" || weather.state === "unknown";
    const condition = unavailable ? null : weather.state;
    const temp = this._num(a.temperature, 0);
    const tempUnit = a.temperature_unit || "°C";
    const meta = [];
    const hum = this._num(a.humidity, 0);
    if (hum !== null) meta.push(`<span title="${esc(t.humidity)}"><ha-icon icon="mdi:water-percent"></ha-icon><b>${hum} %</b></span>`);
    const wind = this._num(a.wind_speed, 0);
    if (wind !== null) {
      const dir = compassPoint(a.wind_bearing, this._lang);
      meta.push(`<span title="${esc(t.wind)}"><ha-icon icon="mdi:weather-windy"></ha-icon><b>${wind} ${esc(a.wind_speed_unit || "km/h")}</b>${dir ? ` ${dir}` : ""}</span>`);
    }
    return `<header class="hero">
      <div class="hero-main">
        <div class="place">${esc(name)}</div>
        <div class="temp-row">
          <span class="temp">${temp === null ? "–" : `${temp}${esc(tempUnit).replace(/^°?/, "°")}`}</span>
          <span class="cond">${esc(condition ? t.condition[condition] || condition : "")}</span>
        </div>
        ${meta.length ? `<div class="meta">${meta.join("")}</div>` : ""}
      </div>
      ${condition ? `<ha-icon class="hero-icon" icon="${conditionIcon(condition, this._isDay(weather))}"></ha-icon>` : ""}
    </header>`;
  }

  /**
   * The "now" detail row: feels-like, UV with the WHO colour, sunrise/sunset,
   * dew point. The weather entity's own attributes come first (HA's standard
   * names), the 0.2.0 sensors are the fallback; each item only when it exists.
   */
  _details(weather, ids) {
    const t = TEXT[this._lang];
    const a = weather.attributes;
    const pick = (attr, id) => {
      const own = this._num(a[attr], 0) !== null ? Number(a[attr]) : null;
      return own !== null ? own : this._sensorNumber(id);
    };
    const items = [];
    const feels = pick("apparent_temperature", ids.apparent);
    if (feels !== null) items.push(`<span title="${esc(t.feelsLikeLong)}">${esc(t.feelsLike)} <b>${this._deg(feels)}</b></span>`);
    const uv = pick("uv_index", ids.uv);
    const level = uvLevel(uv);
    // UV 0 at night says nothing; UV 0 by day ("low") does.
    if (level && !(uv === 0 && this._isDay(weather) === false)) {
      const uvMax = this._sensorNumber(ids.uvMax);
      const max = uvMax !== null && uvMax > uv ? ` <span class="uv-max">${esc(fill(t.uvMax, { n: this._num(uvMax, 0) }))}</span>` : "";
      items.push(`<span title="${esc(`${t.uvLong}: ${t.uvLevel[level.key]}`)}">${esc(t.uv)} <b>${this._num(uv, 0)}</b><i class="uv-dot" style="background:${level.color}"></i>${max}</span>`);
    }
    const sun = this._hass.states["sun.sun"];
    const rising = sun && Date.parse(sun.attributes.next_rising || "");
    const setting = sun && Date.parse(sun.attributes.next_setting || "");
    if (Number.isFinite(rising)) items.push(`<span title="${esc(t.sunrise)}"><ha-icon icon="mdi:weather-sunset-up"></ha-icon><b>${esc(this._clock(rising))}</b></span>`);
    if (Number.isFinite(setting)) items.push(`<span title="${esc(t.sunset)}"><ha-icon icon="mdi:weather-sunset-down"></ha-icon><b>${esc(this._clock(setting))}</b></span>`);
    const dew = pick("dew_point", ids.dewPoint);
    if (dew !== null) items.push(`<span title="${esc(t.dewPointLong)}">${esc(t.dewPoint)} <b>${this._deg(dew)}</b></span>`);
    return items.length ? `<div class="details">${items.join("")}</div>` : "";
  }

  _nextHour(rain, nowMs) {
    const t = TEXT[this._lang];
    // No sensor, or outside the nowcast coverage: the block disappears rather than lying.
    if (!rain || rain.state === "unavailable" || rain.state === "unknown") return "";
    const model = nextHourModel(rain.attributes, nowMs);
    if (!model) return "";
    const sentence = nextHourSentence(model, this._lang, (ms) => this._clock(ms));
    const soft = /^(maybe|dry-uncertain|stale|no-data)/.test(model.kind) || model.kind === "maybe-now";
    const ageOld = model.ageMinutes >= AGEING_MINUTES;
    const sourceWord = model.source === "model" ? t.model : t.radar;
    const age = `${sourceWord} · ${fill(t.ago, { n: model.ageMinutes })}`;

    // One slot per 10 minutes from "now" to +180.
    const byMinute = new Map(model.slots.map((s) => [s.minutes, s]));
    const slots = [];
    for (let m = 0; m <= HORIZON_MINUTES; m += STEP_MINUTES) {
      const s = byMinute.get(m);
      if (!s || s.band === null) { slots.push(`<i class="slot unknown"></i>`); continue; }
      const f = BAND_FRACTION[s.band];
      const h = f ? Math.round(8 + 28 * f) : 3;
      slots.push(`<i class="slot ${s.band}${s.uncertain ? " uncertain" : ""}" style="height:${h}px"></i>`);
    }
    const axis = [t.now, 60, 120, 180].map((m, i) => (i === 0 ? m : this._clock(nowMs + m * 60000)));
    const anyUncertain = model.slots.some((s) => s.uncertain && s.band !== null);
    return `<section class="nexthour${model.kind === "stale" ? " stale" : ""}">
      <div class="label-row"><span class="label">${esc(t.nextHours)}</span><span class="age${ageOld ? " old" : ""}">${esc(age)}</span></div>
      <p class="sentence${soft ? " soft" : ""}">${esc(sentence)}</p>
      <div class="strip" role="img" aria-label="${esc(sentence)}">${slots.join("")}</div>
      <div class="axis">${axis.map((x) => `<span>${esc(x)}</span>`).join("")}</div>
      ${anyUncertain ? `<div class="legend">${esc(t.uncertainLegend)}</div>` : ""}
    </section>`;
  }

  _warnings(sensor, nowMs, compactMode = null) {
    const t = TEXT[this._lang];
    if (!sensor || sensor.state === "unavailable" || sensor.state === "unknown") return "";
    const schedule = warningSchedule(sensor.attributes.warnings, nowMs);
    const all = compactMode ? compactWarnings(schedule, compactMode) : schedule;
    if (!all.length) return "";
    const shown = this._warningsExpanded ? all : all.slice(0, WARNINGS_FOLD);
    const banners = shown.map((w) => {
      const title = `${t.warning[w.level]}${w.phenomenon_name ? ` · ${w.phenomenon_name}` : ""}`;
      // An active warning says until when, an upcoming one from when.
      const ms = w.phase === "upcoming" ? w.onsetMs : w.expiresMs;
      const when = ms !== null ? validityText(w.phase, this._relDay(ms, nowMs), this._clock(ms), this._lang) : "";
      return `<div class="warn${w.phase === "upcoming" ? " upcoming" : ""}" style="--warn:${WARN_COLOR[w.level]}">
        <ha-icon icon="${w.phase === "upcoming" ? "mdi:alert-outline" : "mdi:alert"}"></ha-icon>
        <div class="warn-body">
          <div class="warn-head"><span class="warn-title">${esc(title)}</span>${when ? `<span class="warn-when">${esc(when)}</span>` : ""}</div>
          ${w.headline ? `<div class="warn-text">${esc(w.headline)}</div>` : ""}
        </div>
      </div>`;
    });
    const hidden = all.length - shown.length;
    const fold = all.length > WARNINGS_FOLD
      ? `<button type="button" class="more">${esc(hidden ? fill(t.moreWarnings, { n: hidden }) : t.lessWarnings)}</button>`
      : "";
    return `<div class="warns">${banners.join("")}${fold}</div>`;
  }

  _hourly(weather, nowMs) {
    const t = TEXT[this._lang];
    const list = this._forecast.hourly;
    if (!Array.isArray(list) || list.length === 0) return "";
    const fromNow = list.filter((h) => Date.parse(h.datetime) >= nowMs - 3600000).slice(0, Math.max(1, this._config.hourly_count));
    if (!fromNow.length) return "";
    // The mm bars appear only when some visible hour is wet; a dry window looks as before.
    const amounts = fromNow.map((h) => (precipBand(h.precipitation) ? Number(h.precipitation) : 0));
    const wet = this._config.show_precipitation && amounts.some((mm) => mm > 0);
    const scale = Math.max(5, ...amounts);
    const unit = weather.attributes.precipitation_unit || "mm";
    const cols = fromNow.map((h, i) => {
      const ms = Date.parse(h.datetime);
      const p = Number(h.precipitation_probability);
      const icon = conditionIcon(h.condition, typeof h.is_daytime === "boolean" ? h.is_daytime : undefined);
      let bar = "";
      if (wet) {
        const mm = amounts[i];
        const band = precipBand(mm);
        const height = band ? Math.max(3, Math.round(18 * Math.min(1, mm / scale))) : 2;
        bar = `<span class="mm">${band ? `${this._num(mm, mm < 10 ? 1 : 0)} ${esc(unit)}` : ""}</span>
        <span class="pbar"><i class="${band || "none"}" style="height:${height}px"></i></span>`;
      }
      return `<div class="hour">
        <span class="h">${esc(this._hourLabel(ms))}</span>
        <ha-icon icon="${icon}"></ha-icon>
        <span class="t">${this._deg(h.temperature)}</span>
        ${bar}
        <span class="p">${Number.isFinite(p) && p >= 10 ? `${this._num(p, 0)} %` : ""}</span>
      </div>`;
    });
    return `<section><div class="label-row"><span class="label">${esc(t.hourly)}</span></div><div class="scroll">${cols.join("")}</div></section>`;
  }

  _daily(weather, nowMs) {
    const t = TEXT[this._lang];
    const list = this._forecast.daily;
    if (!Array.isArray(list) || list.length === 0) return "";
    const days = list.slice(0, Math.max(1, this._config.daily_count));
    const his = days.map((d) => Number(d.temperature)).filter(Number.isFinite);
    const los = days.map((d) => Number(d.templow)).filter(Number.isFinite);
    const min = Math.min(...los, ...his);
    const max = Math.max(...his, ...los);
    const span = Math.max(1, max - min);
    const rows = days.map((d) => {
      const ms = Date.parse(d.datetime);
      const lo = Number(d.templow);
      const hi = Number(d.temperature);
      const left = Number.isFinite(lo) ? ((lo - min) / span) * 100 : 0;
      const right = Number.isFinite(hi) ? ((max - hi) / span) * 100 : 0;
      const p = Number(d.precipitation_probability);
      return `<div class="day">
        <span class="d">${esc(this._dayLabel(ms, nowMs))}</span>
        <ha-icon icon="${conditionIcon(d.condition, true)}"></ha-icon>
        <span class="p">${Number.isFinite(p) && p >= 10 ? `${this._num(p, 0)} %` : ""}</span>
        <span class="lo">${this._deg(d.templow)}</span>
        <span class="bar"><i style="left:${left.toFixed(1)}%;right:${right.toFixed(1)}%"></i></span>
        <span class="hi">${this._deg(d.temperature)}</span>
      </div>`;
    });
    return `<section><div class="label-row"><span class="label">${esc(t.daily)}</span></div>${rows.join("")}</section>`;
  }
}

if (typeof customElements !== "undefined" && !customElements.get("meteoveo-card")) {
  customElements.define("meteoveo-card", MeteoVeoCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "meteoveo-card",
    name: "MeteoVeo",
    description: "Current weather with feels-like, UV and sun times; the next 3 hours of rain in 10-minute steps; AEMET warnings with their validity; hourly (with mm) and daily forecast. Compact mode available.",
    preview: true,
    documentationURL: "https://github.com/meteoveo/ha-meteoveo/blob/main/docs/card.md",
  });
  console.info(`%c MeteoVeo card %c ${CARD_VERSION} `, "background:#2f7d63;color:#f1f8f4;font-weight:600", "background:#12302b;color:#f1f8f4");
}
