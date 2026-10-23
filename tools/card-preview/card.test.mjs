// Pure-helper tests for the MeteoVeo card: `node --test tools/card-preview/`.
// The card module defines its element only when a DOM exists, so Node can
// import it for the helpers alone.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  nextHourModel, nextHourSentence, compassPoint, pickLanguage, conditionIcon,
  uvLevel, precipBand, warningSchedule, validityText, compactWarnings,
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
