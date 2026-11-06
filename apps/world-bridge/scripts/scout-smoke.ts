/**
 * npm run scout:smoke
 *
 * LIVE: one real Groq call with fixed facts, the exact body the scout sends (src/scout/groq.ts):
 * the owner's listed run (ANY-6PS, 1:46.90, laps 2140/2165/2109) against the six default BOT
 * variants. Prints the model, the latency, the parsed answer and the fact check's verdict on the
 * model's sentence (and our template sentence). If Groq refuses a parameter, its error message is
 * printed: drop that parameter in groqBody and pin the body in test/scout-groq.test.ts.
 *
 * Needs GROQ_API_KEY in apps/world-bridge/.env. Never prints the key.
 */
import { factsFor, type Candidate } from "../src/scout/eligible.js";
import { groqBody, readAnswer } from "../src/scout/groq.js";
import { factCheck, templateText } from "../src/scout/text.js";
import { die, loadEnv } from "./arkiv-common.js";

const cfg = loadEnv();
const g = cfg.groq;
if (!/^[\x21-\x7e]{8,512}$/.test(g.apiKey)) die("GROQ_API_KEY is not set in apps/world-bridge/.env (console.groq.com, API Keys). Never paste it in chat.");

const YOU = { frames: 6414, splits: [2140, 2165, 2109] };
const VARIANTS: Array<[string, number[]]> = [
  ["BOT-A1", [2087, 1995, 2088]],
  ["BOT-A2", [2248, 1994, 1994]],
  ["BOT-A3", [2087, 2088, 1994]],
  ["BOT-A4", [2168, 2078, 1994]],
  ["BOT-A5", [2087, 2080, 2077]],
  ["BOT-A6", [2168, 2078, 2079]],
];
const cands = VARIANTS.map(([name, laps]) => ({ name, frames: laps.reduce((a, b) => a + b, 0), splits: laps }) as unknown as Candidate).sort((a, b) => a.frames - b.frames);
const facts = factsFor("MARINE DRIVE GP", YOU, cands);
const body = groqBody(g.model, facts);
const redact = (t: string) => t.split(g.apiKey).join("<key>");

console.log(`model    ${g.model} at ${g.base}/chat/completions (timeout ${g.timeoutMs} ms)`);
const t0 = performance.now();
let res: Response;
try {
  res = await fetch(`${g.base}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${g.apiKey}` },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(Number.isInteger(g.timeoutMs) && g.timeoutMs > 0 ? g.timeoutMs : 6000),
  });
} catch (err) {
  die(`no answer: ${(err as Error).name} (${Math.round(performance.now() - t0)} ms)`);
}
const ms = Math.round(performance.now() - t0);
const text = await res.text();
console.log(`status   ${res.status} in ${ms} ms${res.headers.get("retry-after") ? ` (retry-after ${res.headers.get("retry-after")})` : ""}`);
let j: any = null;
try {
  j = JSON.parse(text);
} catch {
  // printed below
}
if (res.status !== 200) die(`Groq refused the request: ${redact(String(j?.error?.message ?? text).slice(0, 400))}${j?.error?.code ? ` (code ${j.error.code})` : ""}`);
const content = j?.choices?.[0]?.message?.content;
console.log(`served   ${String(j?.model ?? "?")}, ${j?.usage?.total_tokens ?? "?"} tokens`);
const a = readAnswer(content, facts);
if (!a) die(`the answer does not fit the enums: ${redact(String(content).slice(0, 300))}`);
const pick = cands[Number(a.pick.slice(1)) - 1];
console.log(`answer   pick ${a.pick} = ${pick.name}, lap ${a.lap}`);
console.log(`reason   ${a.reason}`);
const fc = factCheck(a.reason, { name: pick.name, laps: 3, you: YOU, it: { frames: pick.frames, splits: pick.splits as number[] }, max: Number.isInteger(g.reasonMax) ? g.reasonMax : 110 });
console.log(`check    ${fc.ok ? "passes: the console shows the model's sentence (text: model)" : `fails (${fc.why}): the console shows our template (text: template)`}`);
console.log(`template ${templateText(pick.name, YOU.splits, pick.splits as number[], a.lap).text}`);
