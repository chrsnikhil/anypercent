/**
 * npm run hedera:agent -- --book ANY-K2Q --game MDGP [--frames 6290]
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
import type { Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { BOOK_RE } from "../src/approvals.js";
import { listingFromRow, SdkArkiv } from "../src/arkiv/client.js";
import { fmtTime } from "../src/arkiv/publish.js";
import { LISTING_ATTRS, q3JustAhead, selectOf } from "../src/arkiv/queries.js";
import { decodePage } from "../src/arkiv/rows.js";
import { GAME_IDS, LISTING_TYPES, REAL } from "../src/arkiv/schema.js";
import { arkivRpcUrl, PRIVATE_KEY_RE } from "../src/config.js";
import { parseMessage } from "../src/hedera/messages.js";
import { decCents } from "../src/hedera/resource.js";
import { arg, die, hashscan, line, loadEnv, mirrorOf } from "./hedera-common.js";

const cfg = loadEnv();
const book = arg("book") ?? "";
const game = arg("game") ?? "";
const youFrames = arg("frames") !== undefined ? Number(arg("frames")) : null;
if (!BOOK_RE.test(book) || !GAME_IDS.includes(game) || (youFrames !== null && !(Number.isInteger(youFrames) && youFrames > 0))) {
  die("Usage: npm run hedera:agent -- --book ANY-XXX --game MDGP [--frames 6290]");
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

// 1. The listed ghost just ahead, from Arkiv.
const arkiv = new SdkArkiv({ rpcUrl: arkivRpcUrl(cfg.arkiv), accessKey: cfg.arkiv.accessKey, checkerAddress: checker });
const asked = [...LISTING_ATTRS];
const res = await arkiv.query(q3JustAhead(game, cfg.arkiv.season, youFrames ?? 0xffffffff, checker, REAL), selectOf(asked), 1);
const page = decodePage(res.data, LISTING_TYPES, asked, REAL.listing, checker);
const target = page.rows[0] ? listingFromRow(page.rows[0]) : null;
if (!target) die(`No listed ${game} ghost ${youFrames ? `ahead of ${fmtTime(youFrames)}` : "on the board"} (Q3 at block ${res.blockNumber}).`);
if (target.book === book) die(`The ghost just ahead is ${book}'s own: PB never buys your own book.`);
const priceC = decCents(target.price);
console.log(
  `PB: ${youFrames ? `YOU ${fmtTime(youFrames)}` : "no time yet"} on ${game}; the listed ghost just ahead is ${target.book} at ${fmtTime(Number(target.frames))}` +
    ` (${target.price} USDC${target.pay_to ? ` to ${target.pay_to}` : ", no payout account: not for sale"}). Buying it, no human in the loop.`,
);
if (!target.pay_to) process.exit(1);

// 2. The same buy() as POST /hedera/buy.
const body = { book, game, seller: target.book, listing: target.key, run: target.run, log_h: target.log_h, frames: Number(target.frames), you_frames: youFrames, price_c: priceC };
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
