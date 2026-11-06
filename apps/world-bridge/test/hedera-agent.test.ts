/**
 * PB's agent (POST /hedera/buy): every guard row, the order (INTENT before signing, RECEIPT after the
 * mirror shows the transfer), once only, caps that count reservations, the late path, and a restart
 * mid-payment. Fake HCS, fake mirror, fake facilitator, fake Arkiv, a fake clock; the paywall is the
 * real one over HTTP, and the payments are real transactions signed offline with a throwaway key.
 */
import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { after, describe, it } from "node:test";
import { encryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { Agent, BuyRefused, localDay, type BuyView } from "../src/hedera/agent.js";
import { txAt, txDash } from "../src/hedera/net.js";
import { buildRequirement, headers as x402headers, paymentRequired } from "../src/hedera/x402.js";
import { purchaseKey } from "../src/store.js";
import { makeLog } from "./fake-arkiv.js";
import { AGENT, FEE_PAYER, SELLER_ACCT, TOPIC, USDC } from "./fake-hedera.js";
import { GHOST, hedera, type Harness, type HarnessOptions } from "./hedera-harness.js";
import { waitFor } from "./helpers.js";

const open: Array<{ close(): Promise<void> }> = [];
after(async () => {
  for (const h of open) await h.close();
});

async function setup(o: HarnessOptions = {}) {
  const h = await hedera(o);
  open.push(h);
  return h;
}

async function done(agent: Agent, id: string): Promise<BuyView> {
  await waitFor(() => agent.view(id)?.stage === "done", 10_000);
  return agent.view(id)!;
}

async function buy(h: Harness, over: Record<string, unknown> = {}, agent: Agent = h.agent): Promise<BuyView & { id: string }> {
  const { id, expires_s } = agent.start(h.body(over));
  assert.equal(expires_s, 240);
  assert.match(id, /^p-[0-9a-f]{8}$/);
  const v = await done(agent, id);
  await Promise.all([...agent.background]);
  return { ...v, id };
}

/** Nothing was signed and the facilitator never heard of it. */
function nothingSigned(h: Harness) {
  assert.equal(h.signs.count, 0, "nothing signed");
  assert.equal(h.fac.calls.length, 0, "the facilitator saw no request");
}

/** Another listed run of the same seller (another log). */
function anotherListing(h: Harness, seed: number, frames = 6100) {
  const log = makeLog("MDGP", 4, frames, 64, 1000 + seed);
  const logH = sha256Hex(log);
  const run = h.arkiv.addRun({ ...h.arkiv.runs[0].spec.values, frames, log_h: logH, log_enc: encryptGhost(GHOST, logH, log) });
  const listing = h.arkiv.addListing(run, { ...h.arkiv.listings[0].spec.values, frames, log_h: logH });
  return { run, listing, log_h: logH, frames };
}

describe("PB buys: the happy path", () => {
  it("pays the listing's pay_to, ends ok with the receipt, and posts INTENT then RECEIPT", async () => {
    const h = await setup();
    const v = await buy(h);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(v.failure, null);
    const receipt = v.data.receipt as string;
    assert.match(receipt, new RegExp(`^${FEE_PAYER.replaceAll(".", "\\.")}@\\d+\\.\\d{9}$`));
    assert.deepEqual(v.data, { receipt, hashscan: `https://hashscan.io/testnet/transaction/${txDash(receipt)}`, late: false });
    assert.deepEqual(h.fac.ops(), ["verify", "settle"]);
    assert.equal(h.signs.count, 1);

    const [intent] = h.hcs.of("INTENT");
    assert.equal(intent.topic, TOPIC);
    assert.deepEqual(Object.keys(intent.json), ["v", "t", "id", "buyer", "seller", "game", "listing", "run", "log_h", "pay_to", "amount", "asset", "why", "left_today"]);
    assert.deepEqual(intent.json, {
      v: 1,
      t: "INTENT",
      id: v.id,
      buyer: h.buyer.book,
      seller: h.seller.book,
      game: "MDGP",
      listing: h.listing,
      run: h.run,
      log_h: h.logH,
      pay_to: SELLER_ACCT,
      amount: "0.10",
      asset: USDC,
      why: { you: 6290, target: 6170 },
      left_today: "0.90",
    });
    const [rc] = h.hcs.of("RECEIPT");
    assert.deepEqual(rc.json, {
      v: 1,
      t: "RECEIPT",
      id: v.id,
      intent: Number(intent.seq),
      tx: receipt,
      from: AGENT,
      pay_to: SELLER_ACCT,
      amount: "0.10",
      asset: USDC,
      run: h.run,
      mirror: "SUCCESS",
      late: false,
    });
    const p = h.store.purchaseFor(purchaseKey(h.buyer.book, "MDGP", h.seller.book, h.run))!;
    assert.equal(p.state, "settled");
    assert.equal(p.receipt, receipt);
    assert.equal(h.store.saleFor(receipt)?.buyer, h.buyer.book);
    assert.ok(h.lines.some((l) => l.includes("INTENT") && l.includes("https://hashscan.io/testnet/transaction/")));
  });

  it("the receipt unlocks the ghost through /arkiv/ghost's payment check (and only that run)", async () => {
    const h = await setup();
    const v = await buy(h);
    assert.equal(await h.payments.accept(v.data.receipt as string, h.run), true);
    assert.equal(await h.payments.accept(v.data.receipt as string, `0x${"cd".repeat(32)}`), false);
  });

  it("over HTTP: POST /hedera/buy then GET /hedera/buy/{id}", async () => {
    const h = await setup();
    const res = await fetch(`${h.base}/hedera/buy`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(h.body()) });
    const started = (await res.json()) as { id: string; expires_s: number };
    assert.equal(res.status, 200);
    assert.equal(started.expires_s, 240);
    let view: BuyView;
    for (;;) {
      view = (await (await fetch(`${h.base}/hedera/buy/${started.id}`)).json()) as BuyView;
      if (view.stage === "done") break;
      await new Promise((r) => setTimeout(r, 5));
    }
    assert.equal(view.ok, true);
    assert.deepEqual(Object.keys(view).sort(), ["data", "failure", "ok", "stage"]);
    const unknown = await fetch(`${h.base}/hedera/buy/p-00000000`);
    assert.deepEqual([unknown.status, await unknown.json()], [404, { error: "unknown_id", failure: "buy_down" }]);
  });
});

describe("PB's guards (one per row; nothing is signed on any refusal)", () => {
  it("buyer book not issued by this bridge: buy_budget", async () => {
    const h = await setup();
    const v = await buy(h, { book: "ANY-ZZZ" });
    assert.deepEqual([v.ok, v.failure, v.data], [false, "buy_budget", {}]);
    nothingSigned(h);
    assert.equal(h.hcs.messages.length, 0);
  });

  it("the buyer's own book: buy_suspended", async () => {
    const h = await setup();
    const v = await buy(h, { seller: h.buyer.book });
    assert.equal(v.failure, "buy_suspended");
    nothingSigned(h);
  });

  it("listing gone, not the checker's, or another seller's: buy_changed with now_price gone", async () => {
    const h = await setup();
    assert.deepEqual(await buy(h, { seller: "ANY-QQQ" }).then((v) => [v.failure, v.data]), ["buy_changed", { now_price: "gone" }]);
    h.arkiv.listings[0].creator = "0x2222222222222222222222222222222222222222";
    assert.deepEqual(await buy(h).then((v) => [v.failure, v.data]), ["buy_changed", { now_price: "gone" }]);
    h.arkiv.listings[0].creator = "0x1111111111111111111111111111111111111111";
    h.arkiv.listings[0].live = false;
    assert.deepEqual(await buy(h).then((v) => [v.failure, v.data]), ["buy_changed", { now_price: "gone" }]);
    nothingSigned(h);
  });

  it("listing price differs (on Arkiv, or from the console's price_c): buy_changed with now_price", async () => {
    const h = await setup();
    h.arkiv.listings[0].spec.values.price = "0.25";
    assert.deepEqual(await buy(h).then((v) => [v.failure, v.data]), ["buy_changed", { now_price: "0.25 USDC" }]);
    h.arkiv.listings[0].spec.values.price = "0.1";
    assert.deepEqual(await buy(h, { price_c: 20 }).then((v) => [v.failure, v.data]), ["buy_changed", { now_price: "0.10 USDC" }]);
    nothingSigned(h);
  });

  it("run gone or changed (log_h, log_enc, live, run key): buy_suspended", async () => {
    const h = await setup();
    assert.equal((await buy(h, { log_h: "0".repeat(64) })).failure, "buy_suspended");
    assert.equal((await buy(h, { run: `0x${"ee".repeat(32)}` })).failure, "buy_suspended");
    const sealed = h.arkiv.runs[0].spec.values.log_enc;
    h.arkiv.runs[0].spec.values.log_enc = undefined;
    assert.equal((await buy(h)).failure, "buy_suspended");
    h.arkiv.runs[0].spec.values.log_enc = sealed;
    h.arkiv.runs[0].live = false;
    assert.equal((await buy(h)).failure, "buy_suspended");
    nothingSigned(h);
  });

  it("no pay_to on the listing: buy_suspended", async () => {
    const h = await setup();
    h.arkiv.listings[0].spec.values.pay_to = undefined;
    assert.equal((await buy(h)).failure, "buy_suspended");
    nothingSigned(h);
  });

  it("pay_to cannot take USDC: buy_suspended; unlimited auto-association passes; the mirror down: buy_down", async () => {
    const h = await setup();
    h.mirror.holdings.delete(`${SELLER_ACCT}|${USDC}`);
    assert.equal((await buy(h)).failure, "buy_suspended");
    nothingSigned(h);

    const h2 = await setup();
    h2.mirror.holdings.delete(`${SELLER_ACCT}|${USDC}`);
    h2.mirror.addAccount(SELLER_ACCT, { maxAuto: -1 });
    assert.equal((await buy(h2)).ok, true);

    const h3 = await setup();
    h3.mirror.down = true;
    assert.equal((await buy(h3)).failure, "buy_down");
    nothingSigned(h3);
  });

  it("price over HEDERA_MAX_PRICE_C: buy_budget", async () => {
    const h = await setup({ maxPriceC: 5 });
    assert.equal((await buy(h)).failure, "buy_budget");
    nothingSigned(h);
  });

  it("the buyer book's daily cap (settled + reserved today): buy_budget", async () => {
    const h = await setup({ bookDayC: 10 });
    const other = anotherListing(h, 1);
    assert.equal((await buy(h, { listing: other.listing, run: other.run, log_h: other.log_h, frames: other.frames })).ok, true);
    h.signs.count = 0;
    h.fac.calls.length = 0;
    assert.equal((await buy(h)).failure, "buy_budget");
    nothingSigned(h);
  });

  it("the agent's daily cap across books: buy_budget", async () => {
    const h = await setup({ agentDayC: 10 });
    h.store.reservePurchase("ANY-XXX|MDGP|ANY-YYY|0xrun", { id: "p-00000001", buyer: "ANY-XXX", game: "MDGP", seller: "ANY-YYY", run: "0xrun", listing: "0xl", pay_to: SELLER_ACCT, price_c: 10, day: localDay(h.clock.now()), state: "reserved", at: 1 }, { bookDayC: 100, agentDayC: 100 });
    assert.equal((await buy(h)).failure, "buy_budget");
    nothingSigned(h);
  });

  it("the agent out of USDC (mirror balance): buy_budget", async () => {
    const h = await setup();
    h.mirror.holdings.set(`${AGENT}|${USDC}`, 50_000n);
    assert.equal((await buy(h)).failure, "buy_budget");
    nothingSigned(h);
  });

  it("already settled for (buyer, game, seller, run): ok with the earlier receipt, nothing paid", async () => {
    const h = await setup();
    const first = await buy(h);
    const second = await buy(h);
    assert.equal(second.id, first.id);
    assert.equal(second.data.receipt, first.data.receipt);
    // after a restart: a new agent on the same store answers from the store
    const fresh = new Agent(h.agentOpts);
    const third = await buy(h, {}, fresh);
    assert.equal(third.id, first.id);
    assert.equal(third.data.receipt, first.data.receipt);
    assert.equal(h.fac.ops().filter((o) => o === "settle").length, 1);
    assert.equal(h.signs.count, 1);
  });

  it("already in flight for the key: the same job id", async () => {
    const h = await setup();
    const a = h.agent.start(h.body());
    const b = h.agent.start(h.body());
    assert.equal(a.id, b.id);
    await done(h.agent, a.id);
    assert.equal(h.signs.count, 1);
  });

  it("a bad body: 400 bad_body", async () => {
    const h = await setup();
    assert.throws(() => h.agent.start({ ...h.body(), log_h: "xyz" }), (e: unknown) => e instanceof BuyRefused && e.status === 400);
    assert.throws(() => h.agent.start({ ...h.body(), game: "DOOM" }), BuyRefused);
    assert.throws(() => h.agent.start({ ...h.body(), you_frames: -1 }), BuyRefused);
    const res = await fetch(`${h.base}/hedera/buy`, { method: "POST", body: "x".repeat(5000) });
    assert.deepEqual([res.status, await res.json()], [400, { error: "bad_body", failure: "buy_down" }]);
  });
});

/** A throwaway paywall that answers 402 with a mutated requirement and records whether anyone paid. */
async function evil402(mutate: (accepts: any[]) => any[]) {
  let paid = false;
  const server: Server = createServer(async (req, res) => {
    if (req.headers["payment-signature"]) paid = true;
    const real = await buildRequirement({ network: "hedera:testnet", payTo: SELLER_ACCT, amount: "100000", asset: USDC, feePayer: FEE_PAYER });
    const pr = paymentRequired({ url: `http://evil${req.url}`, description: "evil", mimeType: "application/json" }, real);
    pr.accepts = mutate([real]);
    res.writeHead(402, { "content-type": "application/json", "PAYMENT-REQUIRED": x402headers.encodeRequired(pr) });
    res.end('{"error":"payment_required"}');
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const handle = { base, paid: () => paid, close: () => new Promise<void>((r) => server.close(() => r())) };
  open.push(handle);
  return handle;
}

describe("PB checks the 402 against the listing (nothing signed on a mismatch)", () => {
  const cases: Array<[string, (a: any[]) => any[], string, Record<string, unknown>?]> = [
    ["two entries", (a) => [a[0], { ...a[0] }], "buy_down"],
    ["another network", (a) => [{ ...a[0], network: "hedera:mainnet" }], "buy_down"],
    ["another asset", (a) => [{ ...a[0], asset: "0.0.5449" }], "buy_down"],
    ["HBAR", (a) => [{ ...a[0], asset: "0.0.0" }], "buy_down"],
    ["maxTimeoutSeconds over 300", (a) => [{ ...a[0], maxTimeoutSeconds: 600 }], "buy_down"],
    ["another scheme", (a) => [{ ...a[0], scheme: "upto" }], "buy_down"],
    ["payTo is not the listing's", (a) => [{ ...a[0], payTo: "0.0.666" }], "buy_suspended"],
    ["another amount", (a) => [{ ...a[0], amount: "200000" }], "buy_changed", { now_price: "0.20 USDC" }],
    ["a fee payer the facilitator does not name", (a) => [{ ...a[0], extra: { feePayer: "0.0.666" } }], "buy_down"],
  ];
  for (const [what, mutate, failure, data] of cases) {
    it(`${what}: ${failure}`, async () => {
      const evil = await evil402(mutate);
      const h = await setup({ resourceBase: evil.base });
      const v = await buy(h);
      assert.equal(v.failure, failure, JSON.stringify(v));
      if (data) assert.deepEqual(v.data, data);
      nothingSigned(h);
      assert.equal(evil.paid(), false);
      assert.equal(h.store.spentOn(localDay(h.clock.now()), h.buyer.book), 0, "the reservation is released");
      if (failure === "buy_suspended") assert.ok(h.lines.some((l) => l.includes("REFUSED payTo")));
    });
  }

  it("X402_FEE_PAYERS pins the fee payers PB accepts", async () => {
    const h = await setup({ feePayersPin: ["0.0.7162784"] });
    const v = await buy(h);
    assert.equal(v.failure, "buy_down");
    nothingSigned(h);
  });
});

describe("PB's order: INTENT before signing, RECEIPT after the mirror", () => {
  it("INTENT is accepted by a node before the payment is built; RECEIPT comes last", async () => {
    const h = await setup();
    await buy(h);
    const order = h.events.filter((e) => ["hcs:INTENT", "signed", "facilitator:verify", "facilitator:settle", "hcs:RECEIPT"].includes(e));
    assert.deepEqual(order, ["hcs:INTENT", "signed", "facilitator:verify", "facilitator:settle", "hcs:RECEIPT"]);
  });

  it("RECEIPT waits for the mirror to show the transfer; mirror 'unseen' after 60 s without it", async () => {
    const h = await setup();
    h.fac.landAfterReads = 3;
    const v = await buy(h);
    assert.equal(v.ok, true);
    assert.equal(h.hcs.of("RECEIPT")[0].json.mirror, "SUCCESS");
    assert.ok(h.mirror.reads.transaction >= 4);

    const h2 = await setup();
    h2.fac.landAfterReads = 1_000_000;
    const t0 = h2.clock.now();
    const v2 = await buy(h2);
    assert.equal(v2.ok, true);
    assert.equal(h2.hcs.of("RECEIPT")[0].json.mirror, "unseen");
    assert.ok(h2.clock.now() - t0 >= 60_000);
  });

  it("INTENT refused: buy_down, nothing signed, the reservation released", async () => {
    const h = await setup();
    h.hcs.refuse = 1;
    const v = await buy(h);
    assert.equal(v.failure, "buy_down");
    nothingSigned(h);
    assert.equal(h.store.spentOn(localDay(h.clock.now())), 0);
  });

  it("RECEIPT's intent is null when INTENT's receipt never came", async () => {
    const h = await setup();
    h.hcs.holdReceipts = true;
    const { id } = h.agent.start(h.body());
    await done(h.agent, id);
    await waitFor(() => h.hcs.of("RECEIPT").length === 1, 10_000);
    assert.equal(h.hcs.of("RECEIPT")[0].json.intent, null);
    h.hcs.land();
  });
});

describe("once only, and caps that count reservations", () => {
  it("two concurrent starts give one job and one payment", async () => {
    const h = await setup();
    const ids = [h.agent.start(h.body()).id, h.agent.start(h.body()).id, h.agent.start(h.body()).id];
    assert.equal(new Set(ids).size, 1);
    await done(h.agent, ids[0]);
    assert.equal(h.fac.ops().filter((o) => o === "settle").length, 1);
  });

  it("two purchases at once against a cap for one: one pays, the other is buy_budget", async () => {
    const h = await setup({ bookDayC: 10 });
    const other = anotherListing(h, 2);
    const a = h.agent.start(h.body());
    const b = h.agent.start(h.body({ listing: other.listing, run: other.run, log_h: other.log_h, frames: other.frames }));
    const [va, vb] = [await done(h.agent, a.id), await done(h.agent, b.id)];
    assert.deepEqual([va.ok, vb.ok].sort(), [false, true]);
    assert.equal([va, vb].find((v) => !v.ok)?.failure, "buy_budget");
    assert.equal(h.fac.ops().filter((o) => o === "settle").length, 1);
    assert.equal(h.store.spentOn(localDay(h.clock.now()), h.buyer.book), 10);
  });

  it("a failed job runs again under the same id", async () => {
    const h = await setup();
    h.hcs.refuse = 1;
    const first = await buy(h);
    assert.equal(first.failure, "buy_down");
    const second = await buy(h);
    assert.equal(second.id, first.id);
    assert.equal(second.ok, true);
  });
});

describe("late receipts", () => {
  it("/settle gives no answer, the mirror shows the transaction later: ok with late: true", async () => {
    const h = await setup();
    h.fac.settleMode = "timeout-lands";
    h.fac.landAfterReads = 12;
    const v = await buy(h);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(v.data.late, true);
    assert.equal(h.hcs.of("RECEIPT")[0].json.late, true);
    // the paywall's own watch records the sale too, so /arkiv/ghost takes the receipt
    assert.equal(await h.payments.accept(v.data.receipt as string, h.run), true);
  });

  it("the mirror never shows it: buy_down once the 120 s window has passed (plus 15 s); the reservation released", async () => {
    const h = await setup();
    h.fac.settleMode = "timeout";
    const t0 = h.clock.now();
    const v = await buy(h);
    assert.equal(v.failure, "buy_down");
    assert.ok(h.clock.now() - t0 >= 120_000, `waited ${h.clock.now() - t0} ms`);
    assert.equal(h.store.spentOn(localDay(h.clock.now())), 0);
    assert.equal(h.hcs.of("RECEIPT").length, 0);
  });

  it("settle refused but the transfer landed: ok (the money moved)", async () => {
    const h = await setup();
    h.fac.settleMode = "refuse-lands";
    const v = await buy(h);
    assert.equal(v.ok, true);
  });

  it("the transaction landed with a failure status: buy_down at once", async () => {
    const h = await setup();
    h.fac.settleMode = "fails-on-chain";
    const t0 = h.clock.now();
    const v = await buy(h);
    assert.equal(v.failure, "buy_down");
    assert.ok(h.clock.now() - t0 < 120_000);
  });

  it("verify refused: buy_down at once, nothing settled", async () => {
    const h = await setup();
    h.fac.verifyRefuse = "invalid_exact_hedera_payload_preflight_failed";
    const v = await buy(h);
    assert.equal(v.failure, "buy_down");
    assert.deepEqual(h.fac.ops(), ["verify"]);
    assert.equal(h.store.spentOn(localDay(h.clock.now())), 0);
  });
});

describe("a restart mid-payment", () => {
  it("a reservation whose transaction landed is settled with that receipt, nothing paid again", async () => {
    const h = await setup();
    const key = purchaseKey(h.buyer.book, "MDGP", h.seller.book, h.run);
    const tx = `${FEE_PAYER}@${Math.floor(h.clock.now() / 1000)}.000000042`;
    h.store.reservePurchase(key, { id: "p-0000abcd", buyer: h.buyer.book, game: "MDGP", seller: h.seller.book, run: h.run, listing: h.listing, pay_to: SELLER_ACCT, price_c: 10, day: localDay(h.clock.now()), state: "reserved", at: 1 }, { bookDayC: 100, agentDayC: 500 });
    h.store.notePurchaseTx(key, tx);
    h.mirror.addTx(tx, "SUCCESS", [
      { account: AGENT, amount: -100000n },
      { account: SELLER_ACCT, amount: 100000n },
    ]);
    const v = await buy(h);
    assert.equal(v.id, "p-0000abcd");
    assert.equal(v.ok, true);
    assert.equal(v.data.receipt, txAt(tx));
    nothingSigned(h);
  });

  it("a reservation with no transaction is let go and the purchase runs", async () => {
    const h = await setup();
    const key = purchaseKey(h.buyer.book, "MDGP", h.seller.book, h.run);
    h.store.reservePurchase(key, { id: "p-0000abce", buyer: h.buyer.book, game: "MDGP", seller: h.seller.book, run: h.run, listing: h.listing, pay_to: SELLER_ACCT, price_c: 10, day: localDay(h.clock.now()), state: "reserved", at: 1 }, { bookDayC: 100, agentDayC: 500 });
    const v = await buy(h);
    assert.equal(v.ok, true);
    assert.equal(h.signs.count, 1);
  });
});
