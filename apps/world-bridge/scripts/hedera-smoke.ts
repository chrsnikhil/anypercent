/**
 * npm run hedera:smoke -- --pay-to 0.0.N [--runs 3]
 *
 * LIVE on Hedera testnet: the go/no-go for the facilitator (spec: Part A live smoke, checkpoint H1).
 * Check status.hedera.com first: never run it during an announced upgrade window. In order, with a
 * HashScan link and the time for each:
 *
 *   1. the operator's HBAR, the agent's HBAR and USDC, the seller's (--pay-to) USDC association;
 *   2. the market topic on the mirror: no admin key, the operator's submit key, no fee schedule key,
 *      no custom fees;
 *   3. one SMOKE message: its receipt's sequence number and running hash, then read back from the
 *      mirror (the lag measured);
 *   4. each facilitator's /supported lists exact on hedera:testnet; its fee payer;
 *   5. a full x402 purchase of 0.01 USDC from a throwaway in-process paywall (the real resource.ts
 *      with a fixed payload) to --pay-to: verify ms, settle ms, the transaction id and its link;
 *   6. the mirror shows that transaction with both token-transfer rows.
 *
 * With --runs N, steps 3 and 5-6 run N times and it ends with their p50. It spends 0.01 USDC per run
 * from the agent to --pay-to, and HCS fees from the operator. Prints ids and links, never a key.
 */
import { createHash, randomBytes } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createClientHederaSigner } from "@x402/hedera";
import { ACCOUNT_RE, DER_KEY_RE } from "../src/config.js";
import { smokeMessage } from "../src/hedera/messages.js";
import { parseDerKey, SdkHedera, transfersMatch, txAt } from "../src/hedera/net.js";
import { ResourceServer, type Offer } from "../src/hedera/resource.js";
import { headers, PaymentBuilder } from "../src/hedera/x402.js";
import { buildServer, type HederaRoutes } from "../src/server.js";
import { Store } from "../src/store.js";
import { arg, die, facilitatorsOf, hashscan, hbar, keyMatches, line, loadEnv, mirrorOf, mustAccount, NETWORK, operator, p50, timed, usdc, why } from "./hedera-common.js";

const cfg = loadEnv();
const h = cfg.hedera;
const payTo = arg("pay-to") ?? "";
const runs = Math.max(1, Math.min(10, Number(arg("runs", "1"))));
if (!ACCOUNT_RE.test(payTo)) die("Usage: npm run hedera:smoke -- --pay-to 0.0.N [--runs 3]   (the seller's account, associated with USDC)");
if (!ACCOUNT_RE.test(h.agentId) || !DER_KEY_RE.test(h.agentKey)) die("Run npm run hedera:setup first (HEDERA_AGENT_ID / HEDERA_AGENT_KEY).");
if (!ACCOUNT_RE.test(h.topicId)) die("Run npm run hedera:setup first (HEDERA_TOPIC_ID).");
const op = operator(cfg);
const mirror = mirrorOf(cfg);
const hcs = new SdkHedera({ operatorId: op.id, operatorKey: h.operatorKey, mirror });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
let failed = false;
const fail = (what: string) => {
  failed = true;
  console.log(`FAIL ${what}`);
};

try {
  // 1. Balances and the seller's association.
  console.log("1. accounts");
  const [opAcct, ms1] = await timed(() => mustAccount(mirror, op.id, "HEDERA_OPERATOR_ID"));
  line("operator", hbar(opAcct.balance), hashscan.account(op.id), ms1);
  const agentAcct = await mustAccount(mirror, h.agentId, "HEDERA_AGENT_ID");
  const agentKey = parseDerKey(h.agentKey);
  if (!keyMatches(agentKey, agentAcct.key)) fail("HEDERA_AGENT_KEY is not the agent account's key");
  const [agentUsdc, ms1b] = await timed(() => mirror.tokenBalance(h.agentId, h.usdc));
  line("agent", `${hbar(agentAcct.balance)}, ${usdc(agentUsdc)}`, hashscan.account(h.agentId), ms1b);
  if (agentUsdc === null || agentUsdc < BigInt(runs) * 10_000n) fail(`the agent needs ${runs * 0.01} USDC (faucet.circle.com, Hedera Testnet, ${h.agentId})`);
  const [sellerOk, ms1c] = await timed(() => mirror.associated(payTo, h.usdc));
  await mustAccount(mirror, payTo, "--pay-to");
  line("seller (--pay-to)", sellerOk ? "can take USDC" : "CANNOT take USDC", hashscan.account(payTo), ms1c);
  if (!sellerOk) fail(`${payTo} is not associated with ${h.usdc}`);

  // 2. The topic.
  console.log("2. market topic");
  const [topic, ms2] = await timed(() => mirror.topic(h.topicId));
  if (!topic) {
    fail(`topic ${h.topicId} not on the mirror`);
  } else {
    const submitOk = keyMatches(op.key, topic.submitKey);
    const ok = topic.adminKey === null && submitOk && topic.feeScheduleKey === null && topic.customFees.length === 0;
    line("topic", `admin_key ${topic.adminKey ? "SET" : "null"}, submit_key ${submitOk ? "the operator's" : "NOT the operator's"}, fee_schedule_key ${topic.feeScheduleKey ? "SET" : "null"}, custom_fees ${topic.customFees.length ? "SET" : "none"}`, hashscan.topic(h.topicId), ms2);
    if (!ok) fail("the topic is not what hedera:setup makes (no admin key, the operator's submit key, no fee keys)");
  }

  // 4. Facilitators (before 3 and 5 so a dead facilitator shows first).
  console.log("4. facilitators");
  const facilitators = facilitatorsOf(cfg);
  for (const port of facilitators.ports) {
    try {
      const [kinds, ms4] = await timed(() => port.supported());
      const k = kinds.find((x) => x.x402Version === 2 && x.scheme === "exact" && x.network === NETWORK);
      line(port.url, k ? `exact on ${NETWORK}, fee payer ${String(k.extra?.feePayer)}` : `does NOT list exact on ${NETWORK}`, k ? hashscan.account(String(k.extra?.feePayer)) : undefined, ms4);
    } catch (err) {
      line(port.url, `unreachable (${why(err)})`);
    }
  }
  const chosen = await facilitators.probe();
  if (!chosen) fail("no facilitator answered /supported with exact on hedera:testnet");
  else line("chosen", `${chosen.port.url} (fee payer ${chosen.feePayer})`);

  // The throwaway paywall: the real resource.ts, a fixed payload, sales in a temp store.
  const tmp = mkdtempSync(join(tmpdir(), "anypercent-smoke-"));
  const salesStore = new Store(tmp, "smoke-only-secret-not-used-for-books-0000");
  const payload = Uint8Array.from(Buffer.concat([Buffer.from("ANYPERCENT SMOKE "), randomBytes(48)]));
  const logH = createHash("sha256").update(payload).digest("hex");
  const listing = `0x${createHash("sha256").update(`smoke-listing-${logH}`).digest("hex")}`;
  const offer: Offer = {
    listing,
    run: `0x${createHash("sha256").update(`smoke-run-${logH}`).digest("hex")}`,
    log_h: logH,
    game: "MDGP",
    seller: "ANY-SMK",
    pay_to: payTo,
    price_c: 1,
    description: "Any% hedera:smoke: a fixed payload for 0.01 USDC",
    open: () => payload,
  };
  const timings: string[] = [];
  let resource: ResourceServer | null = null;
  const routes = { x402: (l: string, s: string | null) => (resource as ResourceServer).handle(l, s), x402Preflight: () => (resource as ResourceServer).preflight() } as unknown as HederaRoutes;
  const server = buildServer({ health: () => ({ world: "off", idkit: false, agentpass: false, approvals: null }), idkit: null, approvals: null, hedera: routes });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const url = `${base}/x402/ghost/${listing}`;
  resource = new ResourceServer({
    source: { offer: async (k) => (k === listing ? offer : null) },
    facilitators,
    store: salesStore,
    mirror,
    network: NETWORK,
    asset: h.usdc,
    base,
    gate: () => null,
    log: (l) => timings.push(l),
  });
  const builder = new PaymentBuilder(createClientHederaSigner(h.agentId, agentKey, { network: NETWORK }), NETWORK, h.usdc);

  const submitMs: number[] = [];
  const lagMs: number[] = [];
  const buyMs: number[] = [];
  const settleMs: number[] = [];
  for (let run = 1; run <= runs && !failed; run++) {
    // 3. One SMOKE message.
    console.log(`3. SMOKE message (run ${run}/${runs})`);
    const t0 = performance.now();
    const accepted = await hcs.submit(h.topicId, smokeMessage(run, new Date().toISOString()));
    const receipt = await accepted.receipt;
    const tReceipt = performance.now();
    submitMs.push(Math.round(tReceipt - t0));
    line("receipt", `#${receipt.seq}, running hash ${receipt.runningHash.slice(0, 16)}... (${receipt.runningHash.length / 2} B)`, hashscan.tx(accepted.tx), Math.round(tReceipt - t0));
    let seen = null;
    for (let i = 0; i < 40 && !seen; i++) {
      const msgs = await mirror.topicMessages(h.topicId, { afterSeq: String(BigInt(receipt.seq) - 1n), limit: 1 }).catch(() => []);
      seen = msgs.find((m) => m.seq === receipt.seq) ?? null;
      if (!seen) await sleep(250);
    }
    if (!seen) fail("the SMOKE message did not show on the mirror within 10 s");
    else {
      const lag = Math.round(performance.now() - tReceipt);
      lagMs.push(lag);
      line("on the mirror", `#${seen.seq}, running hash v${seen.runningHashVersion} ${seen.runningHash === receipt.runningHash ? "matches" : "DIFFERS"}`, hashscan.message(seen.consensusAt), lag);
    }

    // 5. A full x402 purchase of 0.01 USDC.
    console.log(`5. x402 purchase of 0.01 USDC to ${payTo} (run ${run}/${runs})`);
    timings.length = 0;
    const tb = performance.now();
    const first = await fetch(url);
    if (first.status !== 402) {
      fail(`the paywall answered ${first.status}, not 402`);
      break;
    }
    const pr = builder.read402((n) => first.headers.get(n), await first.json());
    const built = await builder.build(pr);
    const paid = await fetch(url, { headers: built.header });
    const body = (await paid.json()) as Record<string, unknown>;
    const total = Math.round(performance.now() - tb);
    if (paid.status !== 200) {
      fail(`paid request answered ${paid.status} ${JSON.stringify(body)} (${timings.join(" | ")})`);
      break;
    }
    const settled = headers.decodeResponse(paid.headers.get("payment-response") ?? "");
    const tx = txAt(settled.transaction) ?? settled.transaction;
    const m = /verify (\d+) ms, settle (\d+) ms/.exec(timings.join(" "));
    if (m) settleMs.push(Number(m[2]));
    buyMs.push(total);
    const logOk = createHash("sha256").update(Buffer.from(String(body.log), "base64")).digest("hex") === logH;
    line("settled", `tx ${tx}, payer ${settled.payer}, verify ${m?.[1] ?? "?"} ms, settle ${m?.[2] ?? "?"} ms, payload ${logOk ? "checks" : "DOES NOT CHECK"}`, hashscan.tx(tx), total);
    if (!logOk) fail("the payload did not hash to its log_h");

    // 6. The mirror shows it.
    let mt = null;
    const tm = performance.now();
    for (let i = 0; i < 60 && !mt; i++) {
      mt = await mirror.transaction(tx).catch(() => null);
      if (!mt) await sleep(500);
    }
    if (!mt) fail("the payment did not show on the mirror within 30 s");
    else {
      const ok = mt.result === "SUCCESS" && transfersMatch(mt, h.usdc, h.agentId, payTo, 10_000n);
      line("6. on the mirror", `${mt.result}, ${ok ? `both token-transfer rows (${h.agentId} -0.01, ${payTo} +0.01)` : "the transfers are NOT the expected ones"}, fee paid by ${tx.split("@")[0]}`, hashscan.tx(tx), Math.round(performance.now() - tm));
      if (!ok) fail("unexpected transfers on the mirror");
    }
  }
  server.close();
  rmSync(tmp, { recursive: true, force: true });

  console.log("");
  if (submitMs.length) console.log(`p50 over ${submitMs.length}: HCS submit->receipt ${p50(submitMs)} ms, receipt->mirror ${p50(lagMs)} ms`);
  if (buyMs.length) console.log(`p50 over ${buyMs.length}: x402 purchase (402, sign, verify, settle) ${p50(buyMs)} ms, settle ${p50(settleMs)} ms. Over 6000 ms: raise the console's pay budget (spec: Risks).`);
  console.log(failed ? "SMOKE RED" : "SMOKE GREEN");
} catch (err) {
  console.log(`SMOKE RED: ${why(err)}`);
  failed = true;
} finally {
  hcs.close();
}
process.exit(failed ? 1 : 0);
