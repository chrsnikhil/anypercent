// The browser version of the film as ONE self-contained HTML file: the compositions bundled with esbuild, every asset
// they load (fonts, CAD, game footage, PB's screens, the two soundtracks) packed into the page and unpacked into blob
// URLs before the film's code runs, so it opens from disk with no server.
//
//   python web/export_segments.py && node web/build.mjs     -> out/Any% Film (browser).html
//   node web/build.mjs --serve                               -> also out/web/ (index.html + app.js), to test over http
// Needs the soundtracks: python post_film.py audio, and CUT=sub python post_film.py audio (out/film_audio*_orig.wav).
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PUB = path.join(ROOT, "public");
const TMP = path.join(ROOT, "out", "web");
const OUT = path.join(ROOT, "out", "Any% Film (browser).html");
fs.mkdirSync(path.join(TMP, "audio"), { recursive: true });

// 1. the code
const shim = path.join(ROOT, "web", "remotion-shim.ts");
const real = path.join(ROOT, "node_modules", "remotion", "dist", "esm", "index.mjs");
const threeShim = path.join(ROOT, "web", "three-shim.tsx");
const threeReal = path.join(ROOT, "node_modules", "@remotion", "three", "dist", "esm", "index.mjs");
const result = await esbuild.build({
  entryPoints: [path.join(ROOT, "web", "main.tsx")], bundle: true, minify: true, format: "iife", platform: "browser", target: "es2020",
  jsx: "automatic", write: false, legalComments: "none", logLevel: "warning",
  define: { "process.env.NODE_ENV": '"production"' },
  plugins: [{
    name: "remotion-shim",
    setup(b) {
      b.onResolve({ filter: /^remotion$/ }, () => ({ path: shim }));
      b.onResolve({ filter: /^remotion-real$/ }, () => ({ path: real }));
      b.onResolve({ filter: /^@remotion\/three$/ }, () => ({ path: threeShim }));
      b.onResolve({ filter: /^remotion-three-real$/ }, () => ({ path: threeReal }));
    },
  }],
});
const app = result.outputFiles[0].text;

// 2. the soundtracks, original sound (the MW3 mix is private viewing only)
for (const [cut, wav] of [["full", "film_audio_orig.wav"], ["sub", "film_audio_sub_orig.wav"]]) {
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", path.join(ROOT, "out", wav), "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
    path.join(TMP, "audio", `${cut}.m4a`)]);
}

// 3. the assets the compositions load with staticFile()
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
const KEEP = [/^fonts\/.*\.ttf$/, /^console\.bin$/, /^game\/(RUSH|MDGP)_atlas\.png$/, /^game\/reel\/[A-Z]{4}\/\d{4}\.png$/, /^board(_m\d+)?\.jpg$/,
  /^breaks_tri_\d\.jpg$/, /^screen\.png$/, /^scanlines\.png$/, /^coach\/screen\/\d{3}\.jpg$/, /^handler\/[a-z_]+\/\d{2}\.jpg$/,
  /^built\/.+\.mp4$/];
const files = walk(PUB).map((f) => [path.relative(PUB, f).split(path.sep).join("/"), f]).filter(([rel]) => KEEP.some((r) => r.test(rel)));
files.push(["audio/full.m4a", path.join(TMP, "audio", "full.m4a")], ["audio/sub.m4a", path.join(TMP, "audio", "sub.m4a")]);
const TYPE = { ".ttf": "font/ttf", ".bin": "application/octet-stream", ".png": "image/png", ".jpg": "image/jpeg", ".m4a": "audio/mp4", ".mp4": "video/mp4" };
const index = [];
const chunks = [];
let off = 0;
for (const [rel, abs] of files) {
  const b = fs.readFileSync(abs);
  index.push([rel, off, b.length, TYPE[path.extname(abs)]]);
  chunks.push(b);
  off += b.length;
}
const pack = Buffer.concat(chunks);

// 4. the page
const css = fs.readFileSync(path.join(ROOT, "web", "page.css"), "utf8");
const boot = `(async () => {
  const say = (t) => { const e = document.getElementById("boot-msg"); if (e) e.textContent = t; };
  try {
    const idx = JSON.parse(document.getElementById("idx").textContent);
    const res = await fetch("data:application/octet-stream;base64," + document.getElementById("pak").textContent.trim());
    const buf = await res.arrayBuffer();
    const map = {};
    // a font's URL keeps its extension in a fragment (blob URLs ignore it): @remotion/fonts reads the format from it
    for (const [p, o, n, t] of idx) map[p] = URL.createObjectURL(new Blob([new Uint8Array(buf, o, n)], { type: t })) + (p.endsWith(".ttf") ? "#" + p.split("/").pop() : "");
    window.__ANY_ASSETS = map;
    document.getElementById("boot").remove();
    const s = document.createElement("script");
    s.textContent = document.getElementById("app").textContent;
    document.body.appendChild(s);
  } catch (e) { say("COULD NOT OPEN THE BRIEFING: " + e); }
})();`;
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Any% // the film, live</title>
<style>${css}</style></head>
<body><div id="root"></div>
<div id="boot"><div class="boot-op">ANY%</div><div id="boot-msg">DECRYPTING BRIEFING</div><div class="boot-bar"><i></i></div></div>
<script id="idx" type="application/json">${JSON.stringify(index)}</script>
<script id="pak" type="application/octet-stream">${pack.toString("base64")}</script>
<script id="app" type="text/plain">${app.replace(/<\/script/gi, "<\\/script")}</script>
<script>${boot}</script>
</body></html>`;
fs.writeFileSync(OUT, html);
console.log(`${OUT}: ${(html.length / 1e6).toFixed(1)} MB (code ${(app.length / 1e6).toFixed(2)} MB, ${files.length} assets ${(pack.length / 1e6).toFixed(1)} MB)`);

if (process.argv.includes("--serve")) {           // a served copy for testing: same page, assets as files
  for (const [rel, abs] of files) {
    fs.mkdirSync(path.dirname(path.join(TMP, rel)), { recursive: true });
    if (!abs.startsWith(TMP)) fs.copyFileSync(abs, path.join(TMP, rel));
  }
  const map = Object.fromEntries(files.map(([rel]) => [rel, rel]));
  fs.writeFileSync(path.join(TMP, "app.js"), app);
  fs.writeFileSync(path.join(TMP, "index.html"), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Any% // the film, live</title><style>${css}</style></head><body><div id="root"></div>
<script>window.__ANY_ASSETS = ${JSON.stringify(map)};</script><script src="app.js"></script></body></html>`);
  console.log("served copy:", TMP);
}
