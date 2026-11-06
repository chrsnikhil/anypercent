// Smoke test of the browser film in Remotion's headless Chrome (GPU through ANGLE): opens the built page at given
// moments, waits for the frame, screenshots it, reports page errors; with --bench, plays muted from each moment in real
// time and reports the frames actually drawn per second.
//
//   node web/smoke.mjs [--sub] [--bench] 14 95 212 ...   -> out/web_shots/t<sec>.png
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { openBrowser } from "@remotion/renderer";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const sub = args.includes("--sub"), bench = args.includes("--bench"), fast = args.includes("--fast"), play = args.includes("--play");
const times = args.filter((a) => !a.startsWith("--")).map(Number);
const page_url = pathToFileURL(path.join(ROOT, "out", "Any% Film (browser).html")).href;
const OUT = path.join(ROOT, "out", "web_shots");
fs.mkdirSync(OUT, { recursive: true });

const browser = await openBrowser("chrome", { chromiumOptions: { gl: "angle" }, viewport: { width: 1600, height: 1250 } });
for (const t of times) {
  const page = await browser.newPage({ context: () => null, logLevel: "error", indent: false, pageIndex: 0, onBrowserLog: null, onLog: () => {} });
  const errors = [];
  let benchLine = null;
  page.on("console", (m) => {
    const text = m.text();
    if (text.startsWith("BENCH")) benchLine = text;
    else if (m.type() === "error") errors.push(text);
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const hash = `#t=${t}${sub ? "&cut=sub" : ""}${bench ? "&bench=6" : ""}${fast ? "&q=fast" : ""}${play ? "&play=1" : ""}`;
  await page.goto({ url: page_url + hash, timeout: 120000 });
  await new Promise((r) => setTimeout(r, bench || play ? 32000 : 9000));          // 3D acts compile shaders on mount
  if (bench) benchLine = await page.evaluate(() => window.__BENCH ?? "BENCH: no result (did the player start?)");
  if (play) benchLine = await page.evaluate(() => `PLAYING, 3D at dpr ${window.__ANY_DPR}`);
  const { value } = await page._client().send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, `${sub ? "sub_" : ""}t${t}.png`), Buffer.from(value.data ?? value, "base64"));
  console.log(`t=${t}`, benchLine ?? "", errors.length ? "ERRORS: " + errors.slice(0, 3).join(" | ") : "no errors");
  await page.close();
}
await browser.close({ silent: true });
