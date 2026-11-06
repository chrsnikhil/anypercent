// Screenshots of public explorer pages for the film (HashScan, the Arkiv explorer, the public board), taken with a
// headless Edge driven over the DevTools protocol: load, wait, dismiss a cookie banner (Reject), scroll, capture.
//   node video/final/tools/webshot.mjs <out.png> <url> [wait_ms=9000] [scrollY=0]
import { spawn } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [out, url, waitArg = "9000", scrollArg = "0"] = process.argv.slice(2);
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const PORT = 9333 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "anypercent-webshot-"));
const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, "--window-size=1600,1000", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 50 && !target; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    target = list.find((t) => t.type === "page");
  } catch { await sleep(200); }
}
if (!target) { edge.kill(); throw new Error("Edge did not start"); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((r) => { const n = ++id; pending.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
const run = (expression) => send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });

await send("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
await send("Page.enable");
await send("Page.navigate", { url });
await sleep(Number(waitArg));
// a cookie banner: Reject (else Accept) if any button says so
await run(`(() => { const b = [...document.querySelectorAll('button, a')]; const pick = b.find(x => /^\\s*reject/i.test(x.textContent)) || b.find(x => /^\\s*(accept|got it|ok)\\s*$/i.test(x.textContent)); if (pick) pick.click(); return !!pick; })()`);
await sleep(1500);
if (Number(scrollArg)) { await run(`window.scrollTo(0, ${Number(scrollArg)})`); await sleep(1200); }
const shot = await send("Page.captureScreenshot", { format: "png" });
writeFileSync(out, Buffer.from(shot.result.data, "base64"));
ws.close();
edge.kill();
console.log("wrote", out);
