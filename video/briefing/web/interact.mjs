// Drives the built page the way a viewer does: the start screen, a cut button, click to pause, Space to resume, M to
// mute. Checks the overlays appear and go, and that the film moves while playing (two screenshots a second apart differ)
// and holds while paused (they match).
//
//   node web/interact.mjs        -> out/web_shots/i_*.png
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { openBrowser } from "@remotion/renderer";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const page_url = pathToFileURL(path.join(ROOT, "out", "Any% Film (browser).html")).href;
const SEGS = JSON.parse(fs.readFileSync(path.join(ROOT, "web", "segments.json"), "utf8"));
const SUB_S = SEGS.sub.reduce((a, r) => a + r.frames, 0) / 60;                  // the submission cut's length, as built
const OUT = path.join(ROOT, "out", "web_shots");
fs.mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await openBrowser("chrome", { chromiumOptions: { gl: "angle" }, viewport: { width: 1600, height: 900 } });
const page = await browser.newPage({ context: () => null, logLevel: "error", indent: false, pageIndex: 0, onBrowserLog: null, onLog: () => {} });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
await page.goto({ url: page_url, timeout: 120000 });
await wait(9000);

const shot = async (name) => {
  const { value } = await page._client().send("Page.captureScreenshot", { format: "png" });
  const b64 = value.data ?? value;
  fs.writeFileSync(path.join(OUT, `i_${name}.png`), Buffer.from(b64, "base64"));
  return b64;
};
const has = (sel) => page.evaluate((s) => !!document.querySelector(s), sel);
const key = async (k, code) => {
  await page._client().send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, text: k === " " ? " " : k });
  await page._client().send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code });
};
const results = [];
const check = (what, ok) => { results.push(`${ok ? "PASS" : "FAIL"}  ${what}`); };

check("start screen shows, no timeline or controls", (await has(".menu")) && !(await has("input[type=range]")));
await shot("menu");
await page.evaluate(() => document.querySelectorAll(".cut")[1].click());           // SUBMISSION CUT
await wait(6000);
check("menu gone after picking a cut", !(await has(".menu")));
const a = await shot("play_a");
await wait(1200);
const b = await shot("play_b");
check("film moves while playing", a !== b);
await page.evaluate(() => document.querySelector(".stage").click());
await wait(800);
check("click pauses: pause card shows", await has(".pause"));
const c = await shot("paused_a");
await wait(1200);
check("film holds while paused", c === (await shot("paused_b")));
await key(" ", "Space");
await wait(800);
check("Space resumes: pause card gone", !(await has(".pause")));
await key("m", "KeyM");
await wait(300);
check("M mutes with a notice", (await page.evaluate(() => document.querySelector(".note")?.textContent ?? "")) === "SOUND OFF");

// the end: two seconds before the submission cut runs out, playing -> the end screen with PLAY AGAIN
await page.goto({ url: "about:blank", timeout: 120000 });                       // a fresh load: the link is read once
await page.goto({ url: page_url + `#t=${(SUB_S - 2.4).toFixed(1)}&cut=sub&play=1`, timeout: 120000 });
await wait(12000);
check("end screen after the last frame", await page.evaluate(() =>
  (document.querySelector(".menu .where")?.textContent ?? "") === "END OF BRIEFING" && document.body.textContent.includes("PLAY AGAIN")));
await shot("end");
check("no page errors", errors.length === 0);

console.log(results.join("\n"));
if (errors.length) console.log("ERRORS:", errors.slice(0, 3).join(" | "));
await page.close();
await browser.close({ silent: true });
