/**
 * npm run hedera:evil402 -- --listing 0x... [--book ANY-XXX] [--evil-pay-to 0.0.N]
 *
 * PB refuses a 402 that names another payTo. Starts a throwaway paywall on another port that
 * answers the listing's 402 exactly as ours would (the facilitator's fee payer, the listed amount,
 * USDC) except payTo, which is another account (--evil-pay-to, default the operator's). Then runs
 * PB's real agent against it (the real guards, Arkiv, mirror and HCS; the agent key) and shows:
 *
 *   - REFUSED payTo (buy_suspended), from the agent's own log;
 *   - nothing was signed (the signer was never called) and the evil paywall never saw a
 *     PAYMENT-SIGNATURE, so no facilitator could have been asked to settle anything.
 *
 * PB's INTENT goes to the market topic first, as in every purchase (a node accepts it before
 * anything could be signed); no RECEIPT follows it. The agent works on a temporary copy of
 * data/state.json, so the running service's state is never written. Prints ids and links only.
 */
import { copyFileSync, existsSync, mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createClientHederaSigner, type ClientHederaSigner } from "@x402/hedera";
import type { Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { SdkArkiv } from "../src/arkiv/client.js";
import { KEY_RE } from "../src/arkiv/queries.js";
import { ACCOUNT_RE, arkivRpcUrl, hederaPayProblems } from "../src/config.js";
import { Agent } from "../src/hedera/agent.js";
import { parseDerKey, SdkHedera } from "../src/hedera/net.js";
import { decCents } from "../src/hedera/resource.js";
import { buildRequirement, centsToAtomic, headers, PaymentBuilder, paymentRequired } from "../src/hedera/x402.js";
import { Store } from "../src/store.js";
import { arg, die, facilitatorsOf, hashscan, line, loadEnv, mirrorOf, NETWORK } from "./hedera-common.js";

const cfg = loadEnv();
const h = cfg.hedera;
const listingKey = (arg("listing") ?? "").toLowerCase();
if (!KEY_RE.test(listingKey)) die("Usage: npm run hedera:evil402 -- --listing 0x<listing key> [--book ANY-XXX] [--evil-pay-to 0.0.N]");
const problems = hederaPayProblems(cfg);
if (problems.length) die(`Hedera payments are not configured: ${problems.join(", ")}`);
const evilPayTo = arg("evil-pay-to") ?? h.operatorId;
if (!ACCOUNT_RE.test(evilPayTo)) die("--evil-pay-to must be 0.0.N");

const checker = privateKeyToAccount(cfg.arkiv.checkerKey as Hex).address;
const arkiv = new SdkArkiv({ rpcUrl: arkivRpcUrl(cfg.arkiv), accessKey: cfg.arkiv.accessKey, checkerAddress: checker });
const listing = await arkiv.getListing(listingKey);
if (!listing) die(`${listingKey} is not a live listing of a stamped run (created by the run's own wallet).`);
if (!listing.pay_to) die(`${listingKey} has no pay_to: it is not for sale (relist it after npm run hedera:payto).`);
if (evilPayTo === listing.pay_to) die("--evil-pay-to must differ from the listing's pay_to.");

// A temporary copy of the store: the running service's data/state.json is never written.
const tmp = mkdtempSync(join(tmpdir(), "anypercent-evil402-"));
const stateFile = join(cfg.dataDir, "state.json");
if (existsSync(stateFile)) copyFileSync(stateFile, join(tmp, "state.json"));
const store = new Store(tmp, cfg.serverSecret);
const book = arg("book") ?? "";
const buyer = book !== "" ? store.recordForBook(book) : undefined;
if (book !== "" && !buyer) die(`${book} is not a record book this bridge issued.`);
const buyerBook = buyer?.book ?? (await (async () => {
  const { readFileSync } = await import("node:fs");
  const books = Object.values((JSON.parse(readFileSync(join(tmp, "state.json"), "utf8")) as { books?: Record<string, { book: string }> }).books ?? {}).map((b) => b.book);
  return books.find((b) => b !== listing.book) ?? die("No record book other than the seller's: pass --book.");
})());

const facilitators = facilitatorsOf(cfg);
const chosen = await facilitators.probe();
if (!chosen) die("No facilitator answered /supported.");

// The evil paywall: our 402, but payTo is another account.
let sawSignature = false;
const evil = createServer(async (req, res) => {
  if (req.headers["payment-signature"]) sawSignature = true;
  const req402 = await buildRequirement({ network: NETWORK, payTo: evilPayTo, amount: centsToAtomic(decCents(listing.price)), asset: h.usdc, feePayer: chosen.feePayer });
  const pr = paymentRequired({ url: `http://evil${req.url}`, description: "Any% ghost (evil copy)", mimeType: "application/json" }, req402);
  res.writeHead(402, { "content-type": "application/json", "PAYMENT-REQUIRED": headers.encodeRequired(pr) });
  res.end('{"error":"payment_required"}');
});
await new Promise<void>((r) => evil.listen(0, "127.0.0.1", r));
const evilBase = `http://127.0.0.1:${(evil.address() as AddressInfo).port}`;

const mirror = mirrorOf(cfg);
const hcs = new SdkHedera({ operatorId: h.operatorId, operatorKey: h.operatorKey, mirror });
let signed = 0;
const real = createClientHederaSigner(h.agentId, parseDerKey(h.agentKey), { network: NETWORK });
const signer: ClientHederaSigner = {
  accountId: real.accountId,
  createPartiallySignedTransferTransaction: async (r) => {
    signed += 1;
    return real.createPartiallySignedTransferTransaction(r);
  },
};
const lines: string[] = [];
const agent = new Agent({
  store,
  arkiv,
  mirror,
  hedera: hcs,
  facilitators,
  builder: new PaymentBuilder(signer, NETWORK, h.usdc),
  topic: h.topicId,
  usdc: h.usdc,
  network: NETWORK,
  agentId: h.agentId,
  resourceBase: evilBase,
  priceC: cfg.arkiv.priceC,
  maxPriceC: h.maxPriceC,
  bookDayC: h.bookDayC,
  agentDayC: h.agentDayC,
  feePayersPin: h.feePayers,
  gate: () => null,
  log: (l) => {
    lines.push(l);
    console.log(`  agent: ${l}`);
  },
});

console.log(`evil paywall at ${evilBase}: the 402 names ${evilPayTo}; the listing pays ${listing.pay_to}`);
const { id } = agent.start({
  book: buyerBook,
  game: listing.game,
  seller: listing.book,
  listing: listing.key,
  run: listing.run,
  log_h: listing.log_h,
  frames: Number(listing.frames),
  you_frames: null,
  price_c: decCents(listing.price),
});
let view = agent.view(id);
for (let i = 0; i < 600 && view?.stage !== "done"; i++) {
  await new Promise((r) => setTimeout(r, 100));
  view = agent.view(id);
}
console.log("");
line("purchase", `${id}: ${view?.ok ? "PAID (unexpected)" : view?.failure}`);
line("REFUSED payTo", lines.some((l) => l.includes("REFUSED payTo")) ? "yes (the 402's payTo is not the listing's pay_to)" : "no");
line("signed", signed === 0 ? "nothing (the signer was never called)" : `${signed} payment(s) (unexpected)`);
line("evil paywall got a payment", sawSignature ? "YES (unexpected)" : "no PAYMENT-SIGNATURE ever arrived");
line("topic", `${h.topicId}: PB's INTENT, and no RECEIPT after it`, hashscan.topic(h.topicId));
evil.close();
hcs.close();
rmSync(tmp, { recursive: true, force: true });
const ok = !view?.ok && view?.failure === "buy_suspended" && signed === 0 && !sawSignature;
console.log(ok ? "EVIL402 REFUSED (as it should be)" : "EVIL402: not the expected refusal (see above)");
process.exit(ok ? 0 : 1);
