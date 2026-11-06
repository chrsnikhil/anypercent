/**
 * PB's agent after scout and pivot: a BOT seller paid to the house end to end, the house and console
 * guards (nothing signed on a refusal), the `why` on every buy_suspended, INTENT with and without the
 * scout's pick (exact bytes, and the size at every field's maximum), and the record step refusing an
 * approval spent on an owner op.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, describe, it } from "node:test";
import { encryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { houseListing, houseRun } from "../src/arkiv/house.js";
import { actionText } from "../src/arkiv/publish.js";
import { Consoles } from "../src/consoles.js";
import type { Agent, BuyView, HeldScout } from "../src/hedera/agent.js";
import { HCS_MAX_BYTES, intentMessage } from "../src/hedera/messages.js";
import { makeLog } from "./fake-arkiv.js";
import { HOUSE, SELLER_ACCT, USDC } from "./fake-hedera.js";
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

async function buy(h: Harness, over: Record<string, unknown> = {}, agent: Agent = h.agent): Promise<BuyView & { id: string }> {
  const { id } = agent.start(h.body(over));
  await waitFor(() => agent.view(id)?.stage === "done", 10_000);
  const v = agent.view(id)!;
  await Promise.all([...agent.background]);
  return { ...v, id };
}

function nothingSigned(h: Harness) {
  assert.equal(h.signs.count, 0, "nothing signed");
  assert.equal(h.fac.calls.length, 0, "the facilitator saw no request");
}

/** A house BOT run and listing on the fake board, as a house batch writes them. */
function addBot(h: Harness, label = "BOT-A2", over: { pay_to?: string; human?: boolean } = {}) {
  const log = makeLog("MDGP", 4, 6236, 64, 4242 + h.arkiv.runs.length);
  const logH = sha256Hex(log);
  const run = h.arkiv.addRun(houseRun({ game: "MDGP", season: 1, rules: 4, frames: 6236, log_h: logH, label, runner: "b07b07b07b07b07b", tool: "arcade_replay sha256:a992006e6280", log_enc: encryptGhost(GHOST, logH, log), splits: [2248, 1994, 1994] }));
  const listing = h.arkiv.addListing(run, { ...houseListing({ game: "MDGP", season: 1, frames: 6236, log_h: logH, priceC: 10, seller: "b07b07b07b07b07b", label, pay_to: over.pay_to ?? HOUSE }), ...(over.human ? { human: true } : {}) });
  const body = { seller: label, listing, run, log_h: logH, frames: 6236 };
  return { log, logH, run, listing, body };
}

describe("a BOT seller, paid to the house", () => {
  it("end to end with the fake facilitator: INTENT names the label, the house account gets the USDC", async () => {
    const h = await setup();
    const bot = addBot(h);
    const v = await buy(h, bot.body);
    assert.equal(v.ok, true, JSON.stringify(v));
    const [intent] = h.hcs.of("INTENT");
    assert.equal(intent.json.seller, "BOT-A2");
    assert.equal(intent.json.pay_to, HOUSE);
    assert.equal(h.mirror.holdings.get(`${HOUSE}|${USDC}`), 100_000n, "0.10 USDC to the house");
    const sale = h.store.saleFor(String(v.data.receipt))!;
    assert.deepEqual([sale.seller, sale.pay_to, sale.buyer], ["BOT-A2", HOUSE, h.buyer.book]);
    const offer = await (await import("../src/hedera/resource.js")).ArkivOffers.prototype.offer.call({ arkiv: h.arkiv, ghostSecret: GHOST }, bot.listing);
    assert.equal(offer?.description, "Any% ghost: MARINE DRIVE GP 1:43.93 by BOT-A2 (generated)");
  });

  it("a label listing that pays another account, or says HUMAN: buy_suspended not_house, nothing signed", async () => {
    const h = await setup();
    const other = addBot(h, "BOT-A3", { pay_to: SELLER_ACCT });
    const v = await buy(h, other.body);
    assert.deepEqual([v.failure, v.data], ["buy_suspended", { why: "not_house" }]);
    const human = addBot(h, "BOT-A4", { human: true });
    const w = await buy(h, human.body);
    assert.deepEqual([w.failure, w.data], ["buy_suspended", { why: "not_house" }]);
    nothingSigned(h);
    assert.equal(h.hcs.of("INTENT").length, 0);
  });

  it("a label that is not the listing's: buy_changed gone; a seller that is neither a book nor a BOT label: 400", async () => {
    const h = await setup();
    const bot = addBot(h);
    const v = await buy(h, { ...bot.body, seller: "BOT-A7" });
    assert.deepEqual([v.failure, v.data], ["buy_changed", { now_price: "gone" }]);
    assert.throws(() => h.agent.start(h.body({ ...bot.body, seller: "TEAM" })), /bad_body/);
    assert.throws(() => h.agent.start(h.body({ ...bot.body, seller: "BOT-A" })), /bad_body/);
    nothingSigned(h);
  });
});

describe("every buy_suspended says why", () => {
  it("own_book, run_changed, no_pay_to, cannot_receive", async () => {
    const h = await setup();
    assert.deepEqual((await buy(h, { seller: h.buyer.book })).data, { why: "own_book" });
    assert.deepEqual((await buy(h, { log_h: "0".repeat(64) })).data, { why: "run_changed" });
    h.arkiv.listings[0].spec.values.pay_to = undefined;
    assert.deepEqual((await buy(h)).data, { why: "no_pay_to" });
    h.arkiv.listings[0].spec.values.pay_to = SELLER_ACCT;
    h.mirror.holdings.delete(`${SELLER_ACCT}|${USDC}`);
    assert.deepEqual((await buy(h)).data, { why: "cannot_receive" });
    nothingSigned(h);
  });
});

describe("spending follows the console's binding", () => {
  async function withConsoles() {
    let reg: Consoles | null = null;
    const h = await setup({ consoles: { canSpend: (id, book) => reg!.canSpend(id, book) } });
    reg = new Consoles({ store: h.store, secret: "test-server-secret-0123456789abcdef-xyz", approvals: null });
    return { h, reg };
  }
  const PI = "a1b2c3d4e5f60718293a4b5c6d7e8f90";

  it("a console bound to the buying book pays; another book's console (or an unbound one) is console_not_linked, nothing signed", async () => {
    const { h, reg } = await withConsoles();
    const unbound = await buy(h, { console: PI });
    assert.deepEqual([unbound.failure, unbound.data], ["buy_suspended", { why: "console_not_linked" }]);
    reg.bindAtSignup(PI, h.seller.book, "signup");
    const others = await buy(h, { console: PI });
    assert.deepEqual([others.failure, others.data], ["buy_suspended", { why: "console_not_linked" }]);
    nothingSigned(h);
    const LAPTOP = "ffeeddccbbaa99887766554433221100";
    reg.bindAtSignup(LAPTOP, h.buyer.book, "signup");
    const ok = await buy(h, { console: LAPTOP });
    assert.equal(ok.ok, true);
    assert.ok(h.lines.some((l) => l.includes("INTENT") && l.includes(`console ${reg.view(LAPTOP).tag}`)));
    assert.ok(!h.lines.join("\n").includes(LAPTOP), "never the console id");
  });

  it("without a console (the hedera:agent CLI) the purchase runs as before and says so", async () => {
    const h = await setup();
    assert.equal((await buy(h)).ok, true);
    assert.ok(h.lines.some((l) => l.includes("INTENT") && l.includes("no console")));
  });
});

describe("INTENT with the scout's pick", () => {
  const held = (h: Harness, listing: string, over: Partial<HeldScout> = {}): HeldScout => ({
    buyer: h.buyer.book,
    game: "MDGP",
    listing,
    intent: { by: "model", model: "openai/gpt-oss-120b", lap: 2, you: [2140, 2165, 2109], it: [2248, 1994, 1994], text: "model", why: "You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s." },
    ...over,
  });

  it("a held pick of this purchase goes on INTENT, after `why`, byte for byte", async () => {
    const scouts = new Map<string, HeldScout>();
    const h = await setup({ scouts: { held: (id) => scouts.get(id) } });
    const bot = addBot(h);
    scouts.set("s-1a2b3c4d", held(h, bot.listing));
    const v = await buy(h, { ...bot.body, scout: "s-1a2b3c4d" });
    assert.equal(v.ok, true, JSON.stringify(v));
    const [intent] = h.hcs.of("INTENT");
    assert.deepEqual(Object.keys(intent.json), ["v", "t", "id", "buyer", "seller", "game", "listing", "run", "log_h", "pay_to", "amount", "asset", "why", "scout", "left_today"]);
    assert.equal(
      Buffer.from(intent.bytes).toString("utf8"),
      `{"v":1,"t":"INTENT","id":"${v.id}","buyer":"${h.buyer.book}","seller":"BOT-A2","game":"MDGP","listing":"${bot.listing}","run":"${bot.run}","log_h":"${bot.logH}","pay_to":"${HOUSE}","amount":"0.10","asset":"${USDC}","why":{"you":6290,"target":6236},` +
        `"scout":{"id":"s-1a2b3c4d","by":"model","model":"openai/gpt-oss-120b","lap":2,"you":[2140,2165,2109],"it":[2248,1994,1994],"text":"model","why":"You lose 2.85 s in lap 2: BOT-A2 runs it in 33.23 s, you in 36.08 s."},"left_today":"0.90"}`,
    );
    assert.ok(h.lines.some((l) => l.includes("the scout's pick, by openai/gpt-oss-120b")));
  });

  it("a rule pick records by rule and a null model", async () => {
    const scouts = new Map<string, HeldScout>();
    const h = await setup({ scouts: { held: (id) => scouts.get(id) } });
    const bot = addBot(h);
    scouts.set("s-0000beef", held(h, bot.listing, { intent: { by: "rule", model: null, lap: 2, you: [2140, 2165, 2109], it: [2248, 1994, 1994], text: "template", why: "BOT-A2 is the listed ghost just ahead of you: 1:43.93 against your 1:46.90." } }));
    await buy(h, { ...bot.body, scout: "s-0000beef" });
    const scout = h.hcs.of("INTENT")[0].json.scout;
    assert.deepEqual([scout.by, scout.model, scout.text], ["rule", null, "template"]);
  });

  it("a scout id for another listing, buyer or an unknown one is ignored: no field, and the log says so", async () => {
    const scouts = new Map<string, HeldScout>();
    const h = await setup({ scouts: { held: (id) => scouts.get(id) } });
    const bot = addBot(h);
    scouts.set("s-11111111", held(h, h.listing));
    const v = await buy(h, { ...bot.body, scout: "s-11111111" });
    assert.equal(v.ok, true);
    assert.equal("scout" in h.hcs.of("INTENT")[0].json, false);
    assert.ok(h.lines.some((l) => l === `PB ${v.id}: scout id ignored (not this purchase)`));
    assert.throws(() => h.agent.start(h.body({ scout: "scout-1" })), /bad_body/);
  });

  it("without a scout id INTENT is exactly as before", async () => {
    const h = await setup();
    await buy(h);
    assert.deepEqual(Object.keys(h.hcs.of("INTENT")[0].json), ["v", "t", "id", "buyer", "seller", "game", "listing", "run", "log_h", "pay_to", "amount", "asset", "why", "left_today"]);
  });

  it("INTENT with every field at its maximum fits one 1024 B chunk", () => {
    const bytes = intentMessage({
      id: "p-ffffffff",
      buyer: "ANY-ZZZZZZZZ",
      seller: "BOT-ZZ8",
      game: "MDGP",
      listing: `0x${"f".repeat(64)}`,
      run: `0x${"e".repeat(64)}`,
      log_h: "d".repeat(64),
      pay_to: "0.0.9999999999",
      amount: "10000.00",
      asset: "0.0.9999999999",
      why: { you: 999_999, target: 999_999 },
      scout: { id: "s-ffffffff", by: "model", model: "m".repeat(48), lap: 4, you: [999_999, 999_999, 999_999, 999_999], it: [999_999, 999_999, 999_999, 999_999], text: "template", why: "w".repeat(110) },
      left_today: "10000.00",
    });
    assert.ok(bytes.length <= HCS_MAX_BYTES, `${bytes.length} B`);
  });
});

describe("the record step and owner-op approvals", () => {
  it("an approval spent on a console op is ls_reused at /hedera/record, and no LISTING goes out", async () => {
    const h = await setup();
    const action = actionText("MARINE DRIVE GP", 6170, 10, SELLER_ACCT);
    h.store.recordApproval("jti-op", h.seller.book, createHash("sha256").update(action).digest("hex"), Math.floor(Date.now() / 1000));
    h.store.spendApprovalFor("jti-op", "console-link:C-7QZP");
    const { id } = h.recorder.start({ book: h.seller.book, jti: "jti-op", action, game: "MDGP", title: "MARINE DRIVE GP", frames: 6170, price_c: 10, pay_to: SELLER_ACCT });
    await waitFor(() => h.recorder.view(id)?.stage === "done");
    assert.equal(h.recorder.view(id)?.failure, "ls_reused");
    assert.equal(h.hcs.of("LISTING").length, 0);
  });
});
