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
 * binary sensor (the 10-minute steps of the next 3 hours) and the warnings
 * sensor. The card never talks to the network on its own.
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
    noEntity: "Añade la integración de MeteoVeo y elige su entidad weather.",
    unavailable: "Sin datos de MeteoVeo ahora mismo",
    humidity: "Humedad",
    wind: "Viento",
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
    noEntity: "Add the MeteoVeo integration and pick its weather entity.",
    unavailable: "MeteoVeo data unavailable right now",
    humidity: "Humidity",
    wind: "Wind",
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
    noEntity: "Afegeix la integració de MeteoVeo i tria la seva entitat weather.",
    unavailable: "Sense dades de MeteoVeo ara mateix",
    humidity: "Humitat",
    wind: "Vent",
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
.warn ha-icon { --mdc-icon-size: 22px; color: var(--warn); flex: none; }
.warn-title { font-size: 14px; font-weight: 600; }
.warn-text { font-size: 12.5px; color: var(--mv-ink-2); margin-top: 2px; line-height: 1.35; }
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
          ],
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
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("MeteoVeo: set `entity` to the MeteoVeo weather entity");
    this._config = {
      show_next_hour: true, show_hourly: true, show_daily: true, show_warnings: true,
      hourly_count: 12, daily_count: 7, ...config,
    };
    this._snapshot = null;
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
    const snap = [
      ids.weather, ids.rain, ids.warnings, this._lang,
      hass.themes && hass.themes.darkMode, hass.locale && hass.locale.time_format,
      ...[ids.weather, ids.rain, ids.warnings, "sun.sun"].map((id) => (id && hass.states[id]) || null),
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
    };
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

  _dayLabel(ms, nowMs) {
    const t = TEXT[this._lang];
    const tz = this._timeZone();
    const dayKey = (x) => { try { return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(x)); } catch (e) { return new Date(x).toDateString(); } };
    const k = dayKey(ms);
    if (k === dayKey(nowMs)) return t.today;
    if (k === dayKey(nowMs + 86400000)) return t.tomorrow;
    try { return new Intl.DateTimeFormat(this._locale(), { weekday: "short", day: "numeric", timeZone: tz }).format(new Date(ms)); } catch (e) { return k; }
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
  }

  _body() {
    const t = TEXT[this._lang];
    const hass = this._hass;
    if (!hass || !this._config) return `<div class="mv"><div class="empty">${esc(t.noEntity)}</div></div>`;
    const ids = this._entityIds();
    const weather = hass.states[ids.weather];
    if (!weather) return `<div class="mv"><div class="empty">${esc(t.noEntity)}</div></div>`;
    const nowMs = Date.now();
    const parts = [this._hero(weather, nowMs)];
    if (weather.state === "unavailable" || weather.state === "unknown") {
      parts.push(`<div class="empty">${esc(t.unavailable)}</div>`);
    } else {
      if (this._config.show_next_hour) parts.push(this._nextHour(ids.rain ? hass.states[ids.rain] : null, nowMs));
      if (this._config.show_warnings) parts.push(this._warnings(ids.warnings ? hass.states[ids.warnings] : null));
      if (this._config.show_hourly) parts.push(this._hourly(weather, nowMs));
      if (this._config.show_daily) parts.push(this._daily(weather, nowMs));
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

  _warnings(sensor) {
    const t = TEXT[this._lang];
    if (!sensor || sensor.state === "unavailable" || sensor.state === "unknown") return "";
    const list = Array.isArray(sensor.attributes.warnings) ? sensor.attributes.warnings : [];
    if (!list.length || Number(sensor.state) === 0) return "";
    const sorted = [...list].sort((a, b) => (WARN_RANK[b.level] || 0) - (WARN_RANK[a.level] || 0));
    const top = sorted[0];
    const level = WARN_COLOR[top.level] ? top.level : "yellow";
    const title = `${t.warning[level]}${top.phenomenon_name ? ` · ${top.phenomenon_name}` : ""}`;
    const more = sorted.length > 1 ? ` <span class="age">${esc(fill(t.moreWarnings, { n: sorted.length - 1 }))}</span>` : "";
    return `<div class="warn" style="--warn:${WARN_COLOR[level]}">
      <ha-icon icon="mdi:alert"></ha-icon>
      <div><div class="warn-title">${esc(title)}${more}</div>${top.headline ? `<div class="warn-text">${esc(top.headline)}</div>` : ""}</div>
    </div>`;
  }

  _hourly(weather, nowMs) {
    const t = TEXT[this._lang];
    const list = this._forecast.hourly;
    if (!Array.isArray(list) || list.length === 0) return "";
    const fromNow = list.filter((h) => Date.parse(h.datetime) >= nowMs - 3600000).slice(0, Math.max(1, this._config.hourly_count));
    if (!fromNow.length) return "";
    const cols = fromNow.map((h) => {
      const ms = Date.parse(h.datetime);
      const p = Number(h.precipitation_probability);
      const icon = conditionIcon(h.condition, typeof h.is_daytime === "boolean" ? h.is_daytime : undefined);
      return `<div class="hour">
        <span class="h">${esc(this._hourLabel(ms))}</span>
        <ha-icon icon="${icon}"></ha-icon>
        <span class="t">${this._deg(h.temperature)}</span>
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
    description: "Current weather, the next 3 hours of rain in 10-minute steps, AEMET warnings, hourly and daily forecast.",
    preview: true,
    documentationURL: "https://github.com/meteoveo/ha-meteoveo/blob/main/docs/card.md",
  });
  console.info(`%c MeteoVeo card %c ${CARD_VERSION} `, "background:#2f7d63;color:#f1f8f4;font-weight:600", "background:#12302b;color:#f1f8f4");
}
