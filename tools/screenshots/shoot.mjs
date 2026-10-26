// README screenshots of the MeteoVeo card, taken from a REAL Home Assistant.
//
// The README must show what a user actually gets, so these are not mock-ups: the
// script signs in to a Home Assistant with a long-lived access token, opens a
// dashboard that holds one `custom:meteoveo-card`, and photographs the card in both
// themes. It also records the radar loop (ADR-0833) as an animation, because a still
// frame cannot show the one thing that loop is for.
//
// Playwright is not a dependency of this repository (the integration itself has none),
// so the script borrows an installed copy. Point PLAYWRIGHT_FROM at any project that
// has Playwright installed - its own `node_modules` is used:
//
//   HA_URL=http://<your-ha>:8123 HA_TOKEN=<long-lived token> \
//   PLAYWRIGHT_FROM=/path/to/a/project/with/playwright \
//   node tools/screenshots/shoot.mjs docs/images
//
// Environment: HA_URL, HA_DASHBOARD (the view path, default `/meteoveo-e2e/0`),
// HA_TOKEN or a token file in HA_TOKEN_FILE, PLAYWRIGHT_FROM, and FRAMES / FRAME_MS for
// the animation. The token is read, never printed.

import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

// Bare `import "playwright"` would resolve against THIS repository, which has no
// dependencies - so the module is required from the project named by PLAYWRIGHT_FROM.
const from = process.env.PLAYWRIGHT_FROM;
if (!from) throw new Error("Set PLAYWRIGHT_FROM to a project that has Playwright installed.");
const { chromium } = createRequire(path.join(path.resolve(from), "package.json"))("playwright");

const HA_URL = process.env.HA_URL ?? "http://192.168.86.16:8123";
const DASHBOARD = process.env.HA_DASHBOARD ?? "/meteoveo-e2e/0";
const OUT = path.resolve(process.argv[2] ?? "docs/images");
const FRAMES = Number(process.env.FRAMES ?? 30);
const FRAME_MS = Number(process.env.FRAME_MS ?? 120);

const token = (
  process.env.HA_TOKEN ?? (process.env.HA_TOKEN_FILE ? readFileSync(process.env.HA_TOKEN_FILE, "utf8") : "")
).trim();
if (!token) throw new Error("No Home Assistant token: set HA_TOKEN or HA_TOKEN_FILE.");

// What the Home Assistant frontend expects in localStorage. `clientId: null` marks a
// long-lived token: the frontend then uses it as is instead of trying to refresh it.
const hassTokens = JSON.stringify({
  access_token: token,
  token_type: "Bearer",
  refresh_token: "",
  expires_in: 315360000,
  expires: Date.now() + 315360000 * 1000,
  hassUrl: HA_URL,
  clientId: null,
});

/** The card renders inside a shadow root; Playwright's CSS engine pierces open roots. */
const CARD = "meteoveo-card";
/**
 * The hero of the animation: the "next 3 hours" block AND the radar loop under it
 * (ADR-0833). They are siblings in the card, not nested, so the two boxes are joined -
 * the sentence above the map is what gives the moving radar its meaning.
 */
const HERO_PARTS = [`${CARD} section.nexthour`, `${CARD} .radar`];
/** The weather entity whose device page carries every entity of the integration. */
const WEATHER_ENTITY = process.env.HA_WEATHER_ENTITY ?? "weather.meteoveo_valencia";
/**
 * The device-page cards that list entities. The element, not the heading: the heading
 * is in Home Assistant's own language, while this tag name is the same everywhere.
 */
const ENTITY_CARD = "ha-device-entities-card";

async function heroBox(page) {
  const boxes = [];
  for (const selector of HERO_PARTS) {
    const box = await page.locator(selector).boundingBox();
    if (box) boxes.push(box);
  }
  if (boxes.length === 0) throw new Error("Neither the next-3-hours block nor the radar is on the card");
  const x = Math.min(...boxes.map((b) => b.x));
  const y = Math.min(...boxes.map((b) => b.y));
  return {
    x,
    y,
    width: Math.max(...boxes.map((b) => b.x + b.width)) - x,
    height: Math.max(...boxes.map((b) => b.y + b.height)) - y,
  };
}

async function openDashboard(browser, colorScheme) {
  const context = await browser.newContext({
    colorScheme,
    viewport: { width: 440, height: 2000 },
    deviceScaleFactor: 2,
    timezoneId: process.env.HA_TZ ?? "Europe/Madrid",
    // The card speaks the Home Assistant user's language, and that follows the browser
    // when the profile is on "Auto". The README is in English, so the pictures are too;
    // HA_LOCALE=es-ES gives the Spanish card.
    locale: process.env.HA_LOCALE ?? "en-GB",
  });
  await context.addInitScript(
    ([value]) => window.localStorage.setItem("hassTokens", value),
    [hassTokens],
  );
  const page = await context.newPage();
  await page.goto(`${HA_URL}${DASHBOARD}`, { waitUntil: "domcontentloaded" });

  // Home Assistant boots the whole frontend before a card exists, and on a small
  // machine that takes well over half a minute - so the wait is generous.
  const card = page.locator(CARD);
  await card.waitFor({ state: "visible", timeout: 120000 });
  // The card paints in stages; the radar image is the last thing to arrive.
  await page
    .waitForFunction(
      (selector) => {
        const host = document.querySelector("home-assistant");
        const find = (root, depth) => {
          if (depth > 12) return null;
          for (const el of root.querySelectorAll("*")) {
            if (el.tagName.toLowerCase() === selector) return el;
            if (el.shadowRoot) {
              const hit = find(el.shadowRoot, depth + 1);
              if (hit) return hit;
            }
          }
          return null;
        };
        const el = host ? find(host.shadowRoot ?? host, 0) : null;
        const img = el?.shadowRoot?.querySelector("img");
        return Boolean(el) && (!img || (img.complete && img.naturalWidth > 0));
      },
      CARD,
      { timeout: 60000 },
    )
    .catch(() => console.warn("  (the radar image never reported as loaded; shooting anyway)"));
  await page.waitForTimeout(1500); // the last layout pass and the icon font
  return { context, page, card };
}

/**
 * Photograph one element by CLIPPING the page.
 *
 * An element screenshot scrolls the element into view first, and Home Assistant's
 * header then lands on top of the card: the 2026-10-26 attempt cut the temperature in
 * half. The card fits in this viewport, so the box is taken as it stands and the page
 * is clipped to it - nothing scrolls, nothing overlaps.
 */
async function shoot(page, selector, file) {
  const box = await page.locator(selector).boundingBox();
  if (!box) throw new Error(`No box for ${selector}`);
  await page.screenshot({ path: file, clip: box });
  return box;
}

/**
 * The device page, clipped to the cards that list the entities. The page is wide, so
 * the viewport grows for the shot and shrinks back; the cards are found by their
 * heading, not by a column position, because the layout reflows with the window.
 */
async function devicePage(page) {
  const response = await fetch(`${HA_URL}/api/template`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ template: `{{ device_id('${WEATHER_ENTITY}') }}` }),
  });
  const deviceId = (await response.text()).trim();
  if (!/^[0-9a-f]{32}$/.test(deviceId)) throw new Error(`the template API gave no device id`);

  await page.setViewportSize({ width: 1000, height: 2200 });
  try {
    await page.goto(`${HA_URL}/config/devices/device/${deviceId}`, { waitUntil: "domcontentloaded" });
    await page.locator("ha-config-device-page").waitFor({ timeout: 120000 });
    await page.locator(ENTITY_CARD).first().waitFor({ timeout: 60000 });
    await page.waitForTimeout(3000); // the state values arrive after the rows

    const box = await page.evaluate((tag) => {
      const found = [];
      const walk = (root, depth) => {
        if (depth > 12) return;
        for (const el of root.querySelectorAll("*")) {
          if (el.tagName.toLowerCase() === tag) {
            const r = el.getBoundingClientRect();
            if (r.height > 0) found.push({ x: r.x, y: r.y, w: r.width, h: r.height });
          }
          if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
        }
      };
      walk(document, 0);
      if (found.length === 0) return null;
      const x = Math.min(...found.map((b) => b.x));
      const y = Math.min(...found.map((b) => b.y));
      return {
        x: Math.max(0, x - 12),
        y: Math.max(0, y - 12),
        width: Math.max(...found.map((b) => b.x + b.w)) - x + 24,
        height: Math.max(...found.map((b) => b.y + b.h)) - y + 24,
      };
    }, ENTITY_CARD);
    if (!box) throw new Error("no entity cards on the device page");
    await page.screenshot({ path: path.join(OUT, "entities.png"), clip: box });
    return deviceId;
  } finally {
    // Whatever happened, the card shots that follow must get the narrow viewport back -
    // on 2026-10-26 a thrown error left it at 1000 px and the dark card came out wider
    // than the light one.
    await page.setViewportSize({ width: 440, height: 2000 });
  }
}

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();

// ONE boot, both themes. Booting the Home Assistant frontend a second time took over
// two minutes on 2026-10-26 while a single boot takes ten seconds, so the theme is
// switched with the media feature instead: Home Assistant's default theme follows
// `prefers-color-scheme`, and the card re-renders when `themes.darkMode` changes.
const { context, page } = await openDashboard(browser, "light");

const light = await shoot(page, CARD, path.join(OUT, "card-light.png"));
console.log(`card-light.png — ${Math.round(light.width)}×${Math.round(light.height)} css px`);

// The radar loop, as an animation: a still frame cannot show what the loop is for.
const framesDir = path.join(OUT, ".radar-frames");
mkdirSync(framesDir, { recursive: true });
const hero = await heroBox(page);
for (let i = 0; i < FRAMES; i += 1) {
  await page.screenshot({ path: path.join(framesDir, `f${String(i).padStart(3, "0")}.png`), clip: hero });
  await new Promise((resolve) => setTimeout(resolve, FRAME_MS));
}
console.log(`${FRAMES} frames of the next-3-hours block (${Math.round(hero.width)}×${Math.round(hero.height)} css px)`);

// The device page: the entities the integration creates. Its own picture goes stale
// fastest, because every new sensor changes it. The device id comes from the template
// API, so nothing here is written down that a reinstall would invalidate.
try {
  const deviceId = await devicePage(page);
  console.log(`entities.png — device page ${deviceId.slice(0, 8)}…`);
} catch (error) {
  console.warn(`  (no device-page picture: ${String(error).slice(0, 120)})`);
}

await page.goto(`${HA_URL}${DASHBOARD}`, { waitUntil: "domcontentloaded" });
await page.locator(CARD).waitFor({ state: "visible", timeout: 120000 });
await page.waitForTimeout(2500);
await page.emulateMedia({ colorScheme: "dark" });
await page.waitForTimeout(2000); // the theme travels through hass.themes to the card
const dark = await shoot(page, CARD, path.join(OUT, "card-dark.png"));
console.log(`card-dark.png — ${Math.round(dark.width)}×${Math.round(dark.height)} css px`);

await context.close();
await browser.close();
console.log(`\nframes in ${framesDir} — build the animation with:\n`);
console.log(`  ffmpeg -y -framerate 8 -i ${framesDir}/f%03d.png -loop 0 -q:v 70 ${path.join(OUT, "card-radar.webp")}`);
