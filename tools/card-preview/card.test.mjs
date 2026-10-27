// Pure-helper tests for the MeteoVeo card: `node --test tools/card-preview/`.
// The card module defines its element only when a DOM exists, so Node can
// import it for the helpers alone.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  nextHourModel, nextHourSentence, compassPoint, pickLanguage, conditionIcon,
  uvLevel, precipBand, warningSchedule, validityText, compactWarnings,
  attributionModel, nextHourHasRain, MeteoVeoCard,
} from "../../custom_components/meteoveo/frontend/meteoveo-card.js";

const ISSUED = Date.parse("2026-10-23T11:50:00Z");
const NOW = ISSUED + 60000;
const clock = (ms) => new Date(ms).toISOString().slice(11, 16); // UTC HH:MM, enough for the tests

function steps(bands, opts = {}) {
  return bands.map((band, i) => ({
    at: new Date(ISSUED + i * 600000).toISOString(),
    lead_minutes: i * 10,
    band,
    source: opts.source || "radar",
    uncertain: (opts.uncertain || []).includes(i),
  }));
}
const fill = (arr, band = "none") => { const out = [...arr]; while (out.length < 19) out.push(band); return out; };
const attrs = (bands, extra = {}, opts = {}) => ({ age_minutes: 1, steps: steps(bands, opts), ...extra });

test("all dry for 3 h → dry sentence", () => {
  const m = nextHourModel(attrs(fill([])), NOW);
  assert.equal(m.kind, "dry");
  assert.equal(nextHourSentence(m, "es", clock), "Sin lluvia en las próximas 3 h");
  assert.equal(nextHourSentence(m, "en", clock), "No rain in the next 3 h");
  assert.equal(nextHourSentence(m, "ca", clock), "Sense pluja en les pròximes 3 h");
});

test("rain starting in 20 min names the strongest band of the segment", () => {
  const m = nextHourModel(attrs(fill(["none", "none", "weak", "moderate", "weak"])), NOW);
  assert.equal(m.kind, "starts");
  assert.equal(m.minutes, 20);
  assert.equal(m.band, "moderate");
  assert.equal(nextHourSentence(m, "es", clock), "Lluvia moderada en ~20 min");
});

test("rain starting far out uses the clock", () => {
  const m = nextHourModel(attrs(fill(["none", "none", "none", "none", "none", "none", "none", "none", "none", "none", "none", "light"], "none")), NOW);
  assert.equal(m.kind, "starts");
  assert.equal(m.band, "weak"); // `light` is an alias of the app's `weak`
  assert.equal(nextHourSentence(m, "es", clock), "Lluvia débil desde las 13:40");
});

test("raining now until the first dry step", () => {
  const m = nextHourModel(attrs(fill(["moderate", "moderate", "weak", "weak"])), NOW);
  assert.equal(m.kind, "ends");
  assert.equal(m.minutes, 40);
  assert.equal(nextHourSentence(m, "es", clock), "Lluvia moderada hasta las 12:30");
  assert.equal(nextHourSentence(m, "en", clock), "Rain until 12:30 (moderate)");
});

test("raining for the whole horizon", () => {
  const m = nextHourModel(attrs(fill([], "heavy")), NOW);
  assert.equal(m.kind, "throughout");
  assert.equal(nextHourSentence(m, "es", clock), "Lluvia fuerte en las próximas 3 h");
});

test("uncertain first wet step is only a maybe", () => {
  const m = nextHourModel(attrs(fill(["none", "weak"]), {}, { uncertain: [1] }), NOW);
  assert.equal(m.kind, "maybe");
  assert.equal(nextHourSentence(m, "es", clock), "Podría llover en ~10 min");
  const now = nextHourModel(attrs(fill(["weak"]), {}, { uncertain: [0] }), NOW);
  assert.equal(now.kind, "maybe-now");
});

test("dry but uncertain later", () => {
  const m = nextHourModel(attrs(fill([]), {}, { uncertain: [6, 7] }), NOW);
  assert.equal(m.kind, "dry-uncertain");
  assert.equal(nextHourSentence(m, "es", clock), "Probablemente sin lluvia · incierto a partir de ~60 min");
});

test("steps that already began are dropped and leads re-based on now", () => {
  // Issued 25 minutes ago: the 20-minute step is "now", so rain at lead 40 is in ~20 min.
  const m = nextHourModel({ age_minutes: 25, steps: steps(fill(["none", "none", "none", "none", "weak", "weak"])) }, ISSUED + 25 * 60000);
  assert.equal(m.slots[0].lead, 20);
  assert.equal(m.kind, "starts");
  assert.equal(m.minutes, 20);
});

test("age derived from issued_at when age_minutes is missing", () => {
  const m = nextHourModel({ issued_at: new Date(ISSUED).toISOString(), steps: steps(fill([])) }, ISSUED + 12 * 60000);
  assert.equal(m.ageMinutes, 12);
  assert.equal(m.slots[0].lead, 10);
});

test("stale nowcast and missing data never throw", () => {
  assert.equal(nextHourModel({ age_minutes: 130, steps: steps(fill([])) }, NOW).kind, "stale");
  assert.equal(nextHourModel(null, NOW), null);
  assert.equal(nextHourModel({ steps: "nope" }, NOW), null);
  assert.equal(nextHourModel({ steps: [] }, NOW), null);
  assert.equal(nextHourModel({ age_minutes: 1, steps: [{ lead_minutes: 0, band: "weird" }] }, NOW).kind, "no-data");
  assert.equal(nextHourSentence(null, "es", clock), "Sin datos de precipitación ahora");
  assert.equal(nextHourSentence(null, "xx", clock), "No precipitation data right now");
});

test("partial coverage: dry for the hour only, or nothing to say", () => {
  const hour = nextHourModel({ age_minutes: 0, steps: steps(["none", "none", "none", "none", "none", "none", "none"]) }, ISSUED);
  assert.equal(hour.kind, "dry-hour");
  const short = nextHourModel({ age_minutes: 0, steps: steps(["none", "none"]) }, ISSUED);
  assert.equal(short.kind, "no-data");
});

test("language, compass and icons", () => {
  assert.equal(pickLanguage("es-ES"), "es");
  assert.equal(pickLanguage("ca"), "ca");
  assert.equal(pickLanguage("de"), "en");
  assert.equal(pickLanguage(undefined), "en");
  assert.equal(compassPoint(113, "es"), "SE");
  assert.equal(compassPoint(270, "es"), "O");
  assert.equal(compassPoint(270, "en"), "W");
  assert.equal(compassPoint(359, "en"), "N");
  assert.equal(compassPoint("x", "en"), "");
  assert.equal(conditionIcon("sunny", true), "mdi:weather-sunny");
  assert.equal(conditionIcon("sunny", false), "mdi:weather-night");
  assert.equal(conditionIcon("partlycloudy", false), "mdi:weather-night-partly-cloudy");
  assert.equal(conditionIcon("nonsense"), "mdi:weather-cloudy");
});

test("Hungarian texts exist for the owner's review", () => {
  assert.equal(pickLanguage("hu-HU"), "hu");
  const m = nextHourModel(attrs(fill(["none", "none", "weak", "moderate", "weak"])), NOW);
  assert.equal(nextHourSentence(m, "hu", clock), "Eső ~20 perc múlva (mérsékelt)");
  const ends = nextHourModel(attrs(fill(["moderate", "moderate", "weak", "weak"])), NOW);
  assert.equal(nextHourSentence(ends, "hu", clock), "Eső 12:30-ig (mérsékelt)");
  assert.equal(compassPoint(270, "hu"), "Ny");
});

test("UV index on the WHO scale", () => {
  assert.equal(uvLevel(0).key, "low");
  assert.equal(uvLevel(2.4).key, "low");
  assert.equal(uvLevel(3).key, "moderate");
  assert.equal(uvLevel("5").key, "moderate");
  assert.equal(uvLevel(6).key, "high");
  assert.equal(uvLevel(7).key, "high");
  assert.equal(uvLevel(8).key, "veryHigh");
  assert.equal(uvLevel(10.4).key, "veryHigh");
  assert.equal(uvLevel(11).key, "extreme");
  assert.equal(uvLevel(14).color, "#b567a4");
  assert.equal(uvLevel(null), null);
  assert.equal(uvLevel(""), null);
  assert.equal(uvLevel("unknown"), null);
  assert.equal(uvLevel(-1), null);
});

test("hourly precipitation on the app's mm scale", () => {
  assert.equal(precipBand(0), null);
  assert.equal(precipBand(0.05), null);
  assert.equal(precipBand(0.1), "weak");
  assert.equal(precipBand(0.9), "weak");
  assert.equal(precipBand(1), "moderate");
  assert.equal(precipBand(4.9), "moderate");
  assert.equal(precipBand(5), "strong");
  assert.equal(precipBand(null), null);
  assert.equal(precipBand(undefined), null);
  assert.equal(precipBand("x"), null);
});

const WARNINGS = [
  { level: "yellow", phenomenon_name: "Tormentas", onset: "2026-10-23T10:00:00Z", expires: "2026-10-23T23:00:00Z" },
  { level: "orange", phenomenon_name: "Lluvias", onset: "2026-10-23T10:00:00Z", expires: "2026-10-23T19:00:00Z" },
  { level: "orange", phenomenon_name: "Costeros", onset: "2026-10-25T06:00:00Z", expires: "2026-10-25T22:00:00Z" },
  { level: "yellow", phenomenon_name: "Viento", onset: "2026-10-24T04:00:00Z", expires: "2026-10-24T16:00:00Z" },
  { level: "red", phenomenon_name: "Caducado", onset: "2026-10-22T10:00:00Z", expires: "2026-10-23T06:00:00Z" },
];

test("warnings: active by level then upcoming by onset, expired dropped", () => {
  const s = warningSchedule(WARNINGS, NOW);
  assert.deepEqual(s.map((w) => [w.phase, w.phenomenon_name]), [
    ["active", "Lluvias"], ["active", "Tormentas"], ["upcoming", "Viento"], ["upcoming", "Costeros"],
  ]);
  assert.equal(s[0].expiresMs, Date.parse("2026-10-23T19:00:00Z"));
  assert.equal(s[2].onsetMs, Date.parse("2026-10-24T04:00:00Z"));
});

test("warnings: two active of the same level end soonest first; no dates = active; bad input never throws", () => {
  const s = warningSchedule([
    { level: "yellow", phenomenon_name: "B", expires: "2026-10-23T23:00:00Z" },
    { level: "yellow", phenomenon_name: "A", expires: "2026-10-23T15:00:00Z" },
    { level: "weird", phenomenon_name: "C" },
    null, "x",
  ], NOW);
  assert.deepEqual(s.map((w) => w.phenomenon_name), ["A", "B", "C"]);
  assert.equal(s[2].level, "yellow");
  assert.equal(s[2].phase, "active");
  assert.deepEqual(warningSchedule(null, NOW), []);
  assert.deepEqual(warningSchedule("nope", NOW), []);
});

test("validity text: until / from, today / tomorrow / a later day, four languages", () => {
  assert.equal(validityText("active", "today", "21:00", "es"), "hasta las 21:00");
  assert.equal(validityText("active", "tomorrow", "01:00", "es"), "hasta mañana a las 01:00");
  assert.equal(validityText("upcoming", "tomorrow", "06:00", "es"), "desde mañana a las 06:00");
  assert.equal(validityText("upcoming", "dom 25", "07:00", "es"), "desde el dom 25 a las 07:00");
  assert.equal(validityText("active", "today", "21:00", "en"), "until 21:00");
  assert.equal(validityText("upcoming", "Sun 25", "7:00 AM", "en"), "from Sun 25 7:00 AM");
  assert.equal(validityText("active", "tomorrow", "01:00", "ca"), "fins demà a les 01:00");
  assert.equal(validityText("upcoming", "today", "18:00", "ca"), "des de les 18:00");
  assert.equal(validityText("active", "today", "21:00", "hu"), "21:00-ig");
  assert.equal(validityText("upcoming", "tomorrow", "06:00", "hu"), "holnap 06:00-tól");
  assert.equal(validityText("upcoming", "V 25.", "07:00", "hu"), "V 25. 07:00-tól");
  assert.equal(validityText("active", "today", "", "es"), "");
  assert.equal(validityText("active", "today", "21:00", "xx"), "until 21:00");
});

test("a reply reused after a 304 shows its true age, not the frozen age_minutes", () => {
  // Run issued at ISSUED; the reply was computed 2 minutes later (its age_minutes: 2),
  // and HA kept it for another 15 minutes because the server answered 304.
  const computed = ISSUED + 2 * 60000;
  const reused = steps(fill(["none", "none", "weak", "weak"])).map((s, i) => ({
    ...s,
    at: new Date(computed + i * 600000).toISOString(),
  }));
  const m = nextHourModel(
    { issued_at: new Date(ISSUED).toISOString(), age_minutes: 2, steps: reused },
    computed + 15 * 60000,
  );
  assert.equal(m.ageMinutes, 17);
  assert.equal(m.slots[0].lead, 10);
  assert.equal(m.minutes, 10);
});


test("compact mode keeps the warnings the owner's option asks for", () => {
  const h = 3600000;
  const list = [
    { level: "yellow", phenomenon_name: "Lluvias", onset: new Date(NOW - h).toISOString(), expires: new Date(NOW + h).toISOString() },
    { level: "orange", phenomenon_name: "Vientos", onset: new Date(NOW - h).toISOString(), expires: new Date(NOW + 2 * h).toISOString() },
    { level: "red", phenomenon_name: "Costeros", onset: new Date(NOW + 5 * h).toISOString(), expires: new Date(NOW + 9 * h).toISOString() },
  ];
  const schedule = warningSchedule(list, NOW);
  assert.deepEqual(compactWarnings(schedule, "severe").map((w) => w.level), ["orange"]);
  assert.deepEqual(compactWarnings(schedule, "all").map((w) => w.level), ["orange", "yellow"]);
  assert.deepEqual(compactWarnings(schedule, "none"), []);
});


// --- The source line (issue #2) --------------------------------------------
//
// The full notice runs to six lines on a narrow panel. Folding it is not the
// same as dropping it: the licences ask for the names, and one tap shows them
// unchanged.

const FULL =
  "Datos: © AEMET, © ECMWF, © CAMS (Copernicus), © IGN, © BDLJE, " +
  "mediciones de estaciones locales, MeteoVeo.";

test("by default the sources are one line, and the line can be opened", () => {
  const folded = attributionModel(FULL, "compact", false, "es");
  assert.equal(folded.text, "Datos: AEMET · MeteoVeo");
  assert.equal(folded.expandable, true);
  assert.equal(folded.expanded, false);
  assert.equal(attributionModel(FULL, "compact", false, "en").text, "Data: AEMET · MeteoVeo");
  assert.equal(attributionModel(FULL, "compact", false, "ca").text, "Dades: AEMET · MeteoVeo");
  assert.equal(attributionModel(FULL, "compact", false, "hu").text, "Adatok: AEMET · MeteoVeo");
  // An unknown language falls back to English rather than to a raw key.
  assert.equal(attributionModel(FULL, "compact", false, "xx").text, "Data: AEMET · MeteoVeo");
});

test("opened, it is the full notice word for word", () => {
  const open = attributionModel(FULL, "compact", true, "es");
  assert.equal(open.text, FULL);
  assert.equal(open.expandable, true);
  assert.equal(open.expanded, true);
});

test("attribution: full is the card as it was -- everything, nothing to open", () => {
  const model = attributionModel(FULL, "full", false, "es");
  assert.equal(model.text, FULL);
  assert.equal(model.expandable, false);
});

test("attribution: off keeps the footer off the card entirely", () => {
  // The owner asked for it to be switchable off. It changes the card, not
  // the data: the notice stays in the entity attribute and in the editor.
  for (const expanded of [false, true]) {
    assert.equal(attributionModel(FULL, "off", expanded, "es"), null);
    assert.equal(attributionModel("Datos: © AEMET, MeteoVeo.", "off", expanded, "hu"), null);
  }
});

test("a notice that already fits is left alone", () => {
  // Folding a single line would hide names for no gain, and the short line
  // would claim sources the notice does not name.
  const short = "Datos: © AEMET, MeteoVeo.";
  const model = attributionModel(short, "compact", false, "es");
  assert.equal(model.text, short);
  assert.equal(model.expandable, false);
});

test("a long notice that does not name AEMET is never summarised as AEMET", () => {
  const other = "Datos: © ECMWF, © CAMS (Copernicus), © IGN, mediciones de estaciones locales, MeteoVeo.";
  const model = attributionModel(other, "compact", false, "es");
  assert.equal(model.text, other);
  assert.equal(model.expandable, false);
});

test("nothing to attribute means nothing is rendered", () => {
  for (const empty of [null, undefined, "", "   "]) {
    assert.equal(attributionModel(empty, "compact", false, "es"), null);
  }
});


test("the card editor ends with the full notice, whatever the option says", () => {
  // This is the one place the full naming cannot be switched off, so the
  // licence holds even for someone who hid the footer.
  MeteoVeoCard._lang = "es";
  MeteoVeoCard._attribution = FULL;
  const form = MeteoVeoCard.getConfigForm();
  const tail = form.schema.slice(-2);
  assert.deepEqual(tail.map((s) => s.type), ["constant", "constant"]);
  assert.equal(tail[0].value, FULL);
  assert.equal(form.computeLabel(tail[0]), "Fuentes de los datos");
  // And a quiet line saying why it is there and where else it lives.
  assert.match(tail[1].value, /licencia/);
  assert.match(tail[1].value, /attribution/);
  // The option itself offers exactly the three positions.
  const option = form.schema.find((s) => s.name === "attribution");
  assert.deepEqual(option.selector.select.options.map((o) => o.value), ["compact", "full", "off"]);
  assert.equal(option.default, "compact");
});

test("the editor says where to look when no card has rendered yet", () => {
  // The config form is static and has no `hass`; it must not invent a list.
  MeteoVeoCard._lang = "en";
  MeteoVeoCard._attribution = null;
  const value = MeteoVeoCard.getConfigForm().schema.slice(-2)[0].value;
  assert.match(value, /Open the card once/);
  assert.doesNotMatch(value, /AEMET/);
});


// --- "Next 3 hours" only when there is rain (a reader's suggestion) --------

test("rain-only: a dry window has nothing to say, a wet one has", () => {
  const dry = nextHourModel(attrs(fill([])), NOW);
  assert.equal(nextHourHasRain(dry), false);
  // Rain at the very end of the three hours still counts -- that is the point
  // of the block.
  const late = nextHourModel(attrs(fill([], "none").map((b, i) => (i === 17 ? "weak" : b))), NOW);
  assert.equal(nextHourHasRain(late), true);
  assert.equal(nextHourHasRain(nextHourModel(attrs(fill(["weak"])), NOW)), true);
});

test("rain-only: an old or empty reply says nothing either way, so it stays away", () => {
  const stale = nextHourModel(attrs(fill(["weak"]), { age_minutes: 200, issued_at: new Date(NOW - 200 * 60000).toISOString() }), NOW);
  assert.equal(stale.kind, "stale");
  assert.equal(nextHourHasRain(stale), false);
  assert.equal(nextHourHasRain(null), false);
});

test("rain-only: an uncertain wet step is still rain", () => {
  // "Podría llover en ~20 min" is exactly the sentence someone who asked for
  // the quiet card still wants to see.
  const maybe = nextHourModel(attrs(fill(["none", "none", "weak", "weak"]), {}, { uncertain: [2, 3] }), NOW);
  assert.equal(maybe.kind, "maybe");
  assert.equal(nextHourHasRain(maybe), true);
});

test("the editor offers the two positions of the next-hours block", () => {
  MeteoVeoCard._lang = "es";
  const option = MeteoVeoCard.getConfigForm().schema.find((s) => s.name === "next_hour_when");
  assert.deepEqual(option.selector.select.options.map((o) => o.value), ["always", "rain"]);
  assert.equal(option.default, "always");
  assert.equal(option.selector.select.options[1].label, "Solo si se espera lluvia");
});
