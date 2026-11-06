/**
 * npm run hedera:agent -- --book ANY-K2Q --game MDGP [--frames 6290]
 * npm run hedera:agent -- --book ANY-6PS --game MDGP --log <best .acl> --scout
 *
 * With --scout, step 1 is PB's scout instead of Q3: the bridge replays the log (YOU's laps), reads
 * the listed ghosts' laps from Arkiv and lets the model on Groq (or the board's rule, and it says
 * which) pick the ghost; the purchase then carries the scout's id, so INTENT records the model and
 * its reason. A terminal purchase names no console.
 *
 * PB with no console: the "agent pays with no human" demo. It
 *   1. reads the listed ghost just ahead of --frames straight from Arkiv (Q3, pinned to the checker;
 *      without --frames, the slowest listed ghost) and says why in one line;
 *   2. runs the same buy() as POST /hedera/buy, on the running bridge (the same store, caps and
 *      guards), and follows its stages;
 *   3. fetches the ghost through /arkiv/ghost with the payment's transaction id and checks its hash
 *      against the listing's log_h;
 *   4. prints the INTENT, the payment and the RECEIPT on HashScan (read back from the mirror).
 *
 * The bridge must be running with Hedera configured (it holds the agent key; this script holds none).
 * Prints ids and links only.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import type { Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { BOOK_RE } from "../src/approvals.js";
import { listingFromRow, SdkArkiv, sellerName } from "../src/arkiv/client.js";
import { fmtTime } from "../src/arkiv/publish.js";
import { LISTING_ATTRS, q3JustAhead, selectOf } from "../src/arkiv/queries.js";
import { decodePage } from "../src/arkiv/rows.js";
import { GAME_IDS, LISTING_TYPES, REAL } from "../src/arkiv/schema.js";
import { arkivRpcUrl, PRIVATE_KEY_RE } from "../src/config.js";
import { parseMessage } from "../src/hedera/messages.js";
import { decCents } from "../src/hedera/resource.js";
import { arg, die, flag, hashscan, line, loadEnv, mirrorOf } from "./hedera-common.js";

const cfg = loadEnv();
const book = arg("book") ?? "";
const game = arg("game") ?? "";
let youFrames = arg("frames") !== undefined ? Number(arg("frames")) : null;
const scoutMode = flag("scout");
const logPath = arg("log");
if (!BOOK_RE.test(book) || !GAME_IDS.includes(game) || (youFrames !== null && !(Number.isInteger(youFrames) && youFrames > 0)) || (scoutMode && !logPath)) {
  die("Usage: npm run hedera:agent -- --book ANY-XXX --game MDGP [--frames 6290] | --log <path to .acl> --scout");
}
if (!PRIVATE_KEY_RE.test(cfg.arkiv.checkerKey)) die("ARKIV_CHECKER_KEY is not set: the checker's address pins every read.");
const checker = privateKeyToAccount(cfg.arkiv.checkerKey as Hex).address;
const base = cfg.hedera.resourceBase;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// The bridge must be up with Hedera payments on.
const health = await fetch(`${base}/health`, { signal: AbortSignal.timeout(5000) })
  .then((r) => r.json() as Promise<Record<string, unknown>>)
  .catch(() => die(`The bridge does not answer at ${base} (npm start; HEDERA_RESOURCE_BASE).`));
if (health.hedera_pay !== true) die(`The bridge says hedera_pay: ${String(health.hedera_pay)} (hedera ${String(health.hedera)}): see its startup log.`);

const arkiv = new SdkArkiv({ rpcUrl: arkivRpcUrl(cfg.arkiv), accessKey: cfg.arkiv.accessKey, checkerAddress: checker });
let target: { seller: string; key: string; run: string; log_h: string; frames: number; price_c: number; pay_to?: string };
let scoutId: string | null = null;
if (scoutMode) {
  // 1. PB's scout, on the running bridge: the model (or the rule) picks among code-eligible ghosts.
  let log: Buffer;
  try {
    log = readFileSync(logPath as string);
  } catch {
    die(`Cannot read ${logPath}.`);
  }
  const s = await fetch(`${base}/scout`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ book, game, log: log.toString("base64"), price_c: cfg.arkiv.priceC }) });
  const sj = (await s.json()) as Record<string, any>;
  if (s.status !== 200) die(`POST /scout: ${s.status} ${sj.error} (${sj.failure})`);
  let sv: Record<string, any> = {};
  let st = "";
  for (const until = Date.now() + 30_000; Date.now() < until; ) {
    sv = (await (await fetch(`${base}/scout/${sj.id}`)).json()) as Record<string, any>;
    if (sv.stage !== st) {
      st = sv.stage;
      line(`scout ${sj.id}`, st);
    }
    if (sv.stage === "done") break;
    await sleep(500);
  }
  if (sv.ok !== true) die(`The scout picked nothing: ${sv.failure ?? "no answer in 30 s"}${sv.data?.why ? ` (${sv.data.why})` : ""}`);
  const d = sv.data;
  youFrames = d.you.frames;
  line("YOU", `${d.you.time}${d.you.splits ? `, laps ${d.you.splits.join("/")}` : ", no lap times"}`);
  line("pick", `${d.pick.name} ${d.pick.time}${d.pick.splits ? `, laps ${d.pick.splits.join("/")}` : ""} (${d.candidates} candidates, ${d.skipped} skipped)`);
  line("picked by", d.by === "model" ? `${d.model} on Groq (lap ${d.lap}, sentence: ${d.text})` : `PB's rule: the ghost just ahead (${d.note})`);
  line("reason", d.reason);
  target = { seller: d.pick.name, key: d.pick.listing, run: d.pick.run, log_h: d.pick.log_h, frames: d.pick.frames, price_c: d.pick.price_c, pay_to: d.pick.pay_to ?? undefined };
  scoutId = sj.id;
  console.log(`PB: buying ${d.pick.name}'s ghost for ${d.pick.price_c / 100} USDC to ${d.pick.pay_to}, no human in the loop. PB's guards still decide.`);
} else {
  // 1. The listed ghost just ahead, from Arkiv.
  const asked = [...LISTING_ATTRS];
  const res = await arkiv.query(q3JustAhead(game, cfg.arkiv.season, youFrames ?? 0xffffffff, checker, REAL), selectOf(asked), 1);
  const page = decodePage(res.data, LISTING_TYPES, asked, REAL.listing, checker);
  const l = page.rows[0] ? listingFromRow(page.rows[0]) : null;
  if (!l) die(`No listed ${game} ghost ${youFrames ? `ahead of ${fmtTime(youFrames)}` : "on the board"} (Q3 at block ${res.blockNumber}).`);
  const seller = sellerName(l);
  if (l.book === book) die(`The ghost just ahead is ${book}'s own: PB never buys your own book.`);
  console.log(
    `PB: ${youFrames ? `YOU ${fmtTime(youFrames)}` : "no time yet"} on ${game}; the listed ghost just ahead is ${seller} at ${fmtTime(Number(l.frames))}` +
      ` (${l.price} USDC${l.pay_to ? ` to ${l.pay_to}` : ", no payout account: not for sale"}). Buying it, no human in the loop.`,
  );
  if (!l.pay_to) process.exit(1);
  target = { seller, key: l.key, run: l.run, log_h: l.log_h, frames: Number(l.frames), price_c: decCents(l.price), pay_to: l.pay_to };
}

// 2. The same buy() as POST /hedera/buy.
const body = { book, game, seller: target.seller, listing: target.key, run: target.run, log_h: target.log_h, frames: target.frames, you_frames: youFrames, price_c: target.price_c, ...(scoutId ? { scout: scoutId } : {}) };
const started = await fetch(`${base}/hedera/buy`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const sj = (await started.json()) as Record<string, any>;
if (started.status !== 200) die(`POST /hedera/buy: ${started.status} ${sj.error} (${sj.failure})`);
let stage = "";
let view: Record<string, any> = {};
const until = Date.now() + 240_000;
while (Date.now() < until) {
  view = (await (await fetch(`${base}/hedera/buy/${sj.id}`)).json()) as Record<string, any>;
  if (view.stage !== stage) {
    stage = view.stage;
    line(`purchase ${sj.id}`, stage);
  }
  if (view.stage === "done") break;
  await sleep(500);
}
if (view.ok !== true) die(`PB did not pay: ${view.failure ?? "no answer in 240 s"}${view.data?.now_price ? ` (now ${view.data.now_price})` : ""}`);
const receipt = String(view.data.receipt);
line("payment", `${receipt}${view.data.late ? " (late)" : ""}`, String(view.data.hashscan));

// 3. The ghost, by the payment's transaction id.
const g = await fetch(`${base}/arkiv/ghost`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ run: target.run, receipt }) });
const gj = (await g.json()) as Record<string, any>;
if (g.status !== 200) die(`/arkiv/ghost refused the receipt: ${g.status} ${gj.error}`);
const sum = createHash("sha256").update(Buffer.from(String(gj.log), "base64")).digest("hex");
line("ghost", sum === target.log_h ? `sha256 matches the listing's log_h (${sum.slice(0, 16)}...)` : "sha256 DOES NOT match log_h");

// 4. INTENT and RECEIPT, read back from the mirror.
const mirror = mirrorOf(cfg);
const topic = cfg.hedera.topicId;
const found: Record<string, { seq: string; at: string }> = {};
const tEnd = Date.now() + 90_000;
let after: string | undefined;
while (Date.now() < tEnd && !(found.INTENT && found.RECEIPT)) {
  const msgs = await mirror.topicMessages(topic, { afterSeq: after, limit: 100 }).catch(() => []);
  for (const m of msgs) {
    after = m.seq;
    const j = parseMessage(m.message);
    if (j && j.id === sj.id && (j.t === "INTENT" || j.t === "RECEIPT")) found[j.t as string] = { seq: m.seq, at: m.consensusAt };
  }
  if (!(found.INTENT && found.RECEIPT)) await sleep(2000);
}
for (const t of ["INTENT", "RECEIPT"]) {
  if (found[t]) line(t, `#${found[t].seq} on ${topic}`, hashscan.message(found[t].at));
  else line(t, "not on the mirror yet (the RECEIPT waits up to 60 s for the transfer rows)");
}
line("topic", topic, hashscan.topic(topic));
