// Pure-helper tests for the MeteoVeo card: `node --test tools/card-preview/`.
// The card module defines its element only when a DOM exists, so Node can
// import it for the helpers alone.
import { test } from "node:test";
import assert from "node:assert/strict";
import { nextHourModel, nextHourSentence, compassPoint, pickLanguage, conditionIcon } from "../../custom_components/meteoveo/frontend/meteoveo-card.js";

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
