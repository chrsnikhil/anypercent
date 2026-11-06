// Render chosen frames as PNGs from one bundle:  node scripts/stills.mjs 120 500 1300 ...
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";

const args = process.argv.slice(2);
const id = isNaN(Number(args[0])) ? args.shift() : "Briefing";
const frames = args.map(Number);
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const chromiumOptions = { gl: "angle" };
const composition = await selectComposition({ serveUrl, id, chromiumOptions });
for (const frame of frames) {
  const t = Date.now();
  await renderStill({ composition, serveUrl, frame, output: `out/stills/${({ Briefing: "f", Title: "t", Dossier: "d" })[id] ?? id.toLowerCase() + "_"}${String(frame).padStart(5, "0")}.png`, chromiumOptions });
  console.log("frame", frame, ((Date.now() - t) / 1000).toFixed(1) + "s");
}
