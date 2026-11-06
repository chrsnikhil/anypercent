/**
 * npm run hedera:verify -- <purchase id | payment transaction id>
 *
 * Re-reads, from the public mirror node only (no key, no bridge), PB's INTENT and RECEIPT on the
 * market topic and the payment transaction, and prints whether they agree:
 *
 *   - RECEIPT.tx is the payment; its result is SUCCESS with both token-transfer rows: RECEIPT.from
 *     sends exactly the amount, RECEIPT.pay_to receives it;
 *   - INTENT and RECEIPT name the same pay_to, amount, asset and run; RECEIPT.intent is INTENT's
 *     sequence number;
 *   - the transaction id's account is the facilitator's fee payer (it paid the network fee);
 *   - the RECEIPT reached consensus after the payment.
 *
 * INTENT's consensus time is printed for reference only: PB submits it before signing the payment
 * and does not wait for its consensus, so its order against the payment is not a claim.
 *
 * Exit code 0 when everything agrees. Prints ids and links only.
 */
import { parseMessage } from "../src/hedera/messages.js";
import { transfersMatch, txAt, type MirrorMessage } from "../src/hedera/net.js";
import { ACCOUNT_RE } from "../src/config.js";
import { die, hashscan, line, loadEnv, mirrorOf, positional } from "./hedera-common.js";

const cfg = loadEnv();
const h = cfg.hedera;
const want = positional()[0] ?? "";
const byId = /^p-[0-9a-f]{8}$/.test(want);
const wantTx = txAt(want);
if (!byId && !wantTx) die("Usage: npm run hedera:verify -- p-3f9c0a1b   (or a payment transaction id, 0.0.X@S.N)");
if (!ACCOUNT_RE.test(h.topicId)) die("HEDERA_TOPIC_ID is not set.");
const mirror = mirrorOf(cfg);

// Every message on the topic (it is small), oldest first; at most 100 pages.
const all: Array<{ m: MirrorMessage; j: Record<string, any> }> = [];
let after: string | undefined;
for (let pages = 0; pages < 100; pages++) {
  const page = await mirror.topicMessages(h.topicId, { afterSeq: after, limit: 100 });
  for (const m of page) {
    const j = parseMessage(m.message);
    if (j) all.push({ m, j });
  }
  if (page.length < 100) break;
  after = page[page.length - 1].seq;
}
const receipt = all.find((x) => x.j.t === "RECEIPT" && (byId ? x.j.id === want : txAt(String(x.j.tx)) === wantTx));
const pid = byId ? want : receipt?.j.id;
const intent = all.find((x) => x.j.t === "INTENT" && x.j.id === pid);
const checks: Array<[string, boolean]> = [];

if (intent) line("INTENT", `#${intent.m.seq} ${pid}: ${intent.j.buyer} buys ${intent.j.seller}'s ${intent.j.game}, ${intent.j.amount} USDC to ${intent.j.pay_to}`, hashscan.message(intent.m.consensusAt));
else line("INTENT", `not found for ${pid ?? want}`);
if (receipt) line("RECEIPT", `#${receipt.m.seq}: tx ${receipt.j.tx}, mirror ${receipt.j.mirror}${receipt.j.late ? ", late" : ""}`, hashscan.message(receipt.m.consensusAt));
else line("RECEIPT", "not found (no payment settled for it, or not yet)");

const txId = receipt ? String(receipt.j.tx) : wantTx;
const tx = txId ? await mirror.transaction(txId) : null;
if (txId) line("payment", tx ? `${tx.result}, consensus ${tx.consensusAt}` : `${txId} is not on the mirror`, hashscan.tx(txId));

checks.push(["INTENT on the topic", intent !== undefined]);
checks.push(["RECEIPT on the topic", receipt !== undefined]);
checks.push(["the payment is on the mirror", tx !== null]);
if (intent && receipt) {
  for (const k of ["pay_to", "amount", "asset", "run"]) checks.push([`INTENT.${k} = RECEIPT.${k}`, intent.j[k] === receipt.j[k]]);
  checks.push(["RECEIPT.intent = INTENT's sequence number", String(receipt.j.intent) === intent.m.seq]);
}
if (tx && receipt) {
  const atomic = BigInt(Math.round(Number(receipt.j.amount) * 100)) * 10_000n;
  checks.push(["SUCCESS with both token-transfer rows", tx.result === "SUCCESS" && transfersMatch(tx, String(receipt.j.asset), String(receipt.j.from), String(receipt.j.pay_to), atomic)]);
  const feePayer = String(receipt.j.tx).split("@")[0];
  const paidFee = tx.id.startsWith(`${feePayer}-`);
  checks.push([`the fee payer ${feePayer} is the transaction's account (not the agent)`, paidFee && feePayer !== receipt.j.from]);
  checks.push(["RECEIPT reached consensus after the payment", receipt.m.consensusAt > tx.consensusAt]);
}
if (tx && intent) line("for reference", `INTENT consensus ${intent.m.consensusAt}, payment consensus ${tx.consensusAt} (INTENT is submitted before signing; its order is not a claim)`);

console.log("");
for (const [what, ok] of checks) console.log(`${ok ? "ok  " : "NO  "} ${what}`);
const agree = checks.every(([, ok]) => ok);
console.log(agree ? "VERIFIED: INTENT, the payment and RECEIPT agree" : "NOT VERIFIED (see above)");
process.exit(agree ? 0 : 1);
