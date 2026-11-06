/** The Hedera module's config gating, /health fields, /hedera/config, the payto and sales routes, 503s and the access log. */
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, describe, it } from "node:test";
import { hederaPayProblems, hederaRecordProblems, loadConfig } from "../src/config.js";
import { HederaService } from "../src/hedera/service.js";
import { Facilitators } from "../src/hedera/x402.js";
import { buildServer, makeHealth } from "../src/server.js";
import { FakeFacilitator } from "./fake-facilitator.js";
import { AGENT, FakeMirror, OPERATOR, SELLER_ACCT, TOPIC, USDC } from "./fake-hedera.js";
import { hedera, type Harness } from "./hedera-harness.js";

const OP_KEY = `302e020100300506032b657004220420${"11".repeat(32)}`;
const AG_KEY = `3030020100300706052b8104000a04220420${"22".repeat(32)}`;
const FULL = {
  SERVER_SECRET: "s".repeat(40),
  ARKIV_CHECKER_KEY: `0x${"1".repeat(64)}`,
  ARKIV_GHOST_SECRET: "ab".repeat(32),
  HEDERA_OPERATOR_ID: "0.0.7001",
  HEDERA_OPERATOR_KEY: OP_KEY,
  HEDERA_AGENT_ID: "0.0.6001234",
  HEDERA_AGENT_KEY: AG_KEY,
  HEDERA_TOPIC_ID: "0.0.8001",
};

const open: Harness[] = [];
after(async () => {
  for (const h of open) await h.close();
});

describe("Hedera config", () => {
  it("defaults: testnet, the public mirror, testnet USDC, x402.org then Blocky402, caps 10/100/500, the resource base from HOST:PORT", () => {
    const h = loadConfig({}, ".").hedera;
    assert.equal(h.network, "testnet");
    assert.equal(h.mirror, "https://testnet.mirrornode.hedera.com");
    assert.equal(h.usdc, "0.0.429274");
    assert.equal(h.facilitator, "https://x402.org/facilitator");
    assert.equal(h.facilitatorFallback, "https://api.testnet.blocky402.com");
    assert.deepEqual([h.maxPriceC, h.bookDayC, h.agentDayC], [10, 100, 500]);
    assert.equal(h.resourceBase, "http://127.0.0.1:8787");
    assert.equal(loadConfig({ HOST: "0.0.0.0", PORT: "9000" }, ".").hedera.resourceBase, "http://127.0.0.1:9000");
    assert.equal(loadConfig({ HOST: "172.18.96.1" }, ".").hedera.resourceBase, "http://172.18.96.1:8787");
    assert.equal(loadConfig({ HEDERA_RESOURCE_BASE: "http://192.168.137.1:8787/" }, ".").hedera.resourceBase, "http://192.168.137.1:8787");
    assert.equal(loadConfig({ HEDERA_MIRROR: "https://m.example/api/v1/" }, ".").hedera.mirror, "https://m.example");
    assert.deepEqual(loadConfig({ X402_FEE_PAYERS: "0.0.1, 0.0.2" }, ".").hedera.feePayers, ["0.0.1", "0.0.2"]);
  });

  it("complete: no problems", () => {
    const c = loadConfig(FULL, ".");
    assert.deepEqual(hederaRecordProblems(c), []);
    assert.deepEqual(hederaPayProblems(c), []);
  });

  it("nothing set: names only, never a value", () => {
    const p = hederaPayProblems(loadConfig({}, "."));
    for (const n of ["HEDERA_OPERATOR_ID", "HEDERA_OPERATOR_KEY", "HEDERA_AGENT_ID", "HEDERA_AGENT_KEY", "HEDERA_TOPIC_ID", "SERVER_SECRET", "ARKIV_CHECKER_KEY", "ARKIV_GHOST_SECRET"]) assert.ok(p.includes(n), n);
    assert.ok(!p.includes("HEDERA_USDC") && !p.includes("X402_FACILITATOR"));
    const leaky = hederaPayProblems(loadConfig({ ...FULL, HEDERA_AGENT_KEY: "deadbeef" }, "."));
    assert.deepEqual(leaky, ["HEDERA_AGENT_KEY"]);
    assert.ok(!JSON.stringify(leaky).includes("deadbeef"));
  });

  it("refused: mainnet, raw hex keys (read as ED25519), EVM aliases, http facilitators, bad caps and pins", () => {
    const p = (over: Record<string, string>) => hederaPayProblems(loadConfig({ ...FULL, ...over }, "."));
    assert.deepEqual(p({ HEDERA_NETWORK: "mainnet" }), ["HEDERA_NETWORK"]);
    assert.deepEqual(p({ HEDERA_OPERATOR_KEY: `0x${"ab".repeat(32)}` }), ["HEDERA_OPERATOR_KEY"]);
    assert.deepEqual(p({ HEDERA_AGENT_ID: "0x53e813a4f255607620b6741b2ec69100e011e048" }), ["HEDERA_AGENT_ID"]);
    assert.deepEqual(p({ X402_FACILITATOR: "http://x402.org/facilitator" }), ["X402_FACILITATOR"]);
    assert.deepEqual(p({ HEDERA_BOOK_DAY_C: "-1" }), ["HEDERA_BOOK_DAY_C"]);
    assert.deepEqual(p({ X402_FEE_PAYERS: "0.0.1,nope" }), ["X402_FEE_PAYERS"]);
    assert.deepEqual(hederaRecordProblems(loadConfig({ ...FULL, HEDERA_TOPIC_ID: "" }, ".")), ["HEDERA_TOPIC_ID"]);
  });
});

describe("/health's Hedera fields", () => {
  function service(o: { agentUsdc?: bigint | null; operatorHbar?: bigint; facDown?: boolean; payProblems?: string[]; recordProblems?: string[]; usdcDecimals?: number } = {}) {
    const mirror = new FakeMirror();
    if (o.agentUsdc === null) mirror.holdings.delete(`${AGENT}|${USDC}`);
    else if (o.agentUsdc !== undefined) mirror.holdings.set(`${AGENT}|${USDC}`, o.agentUsdc);
    if (o.operatorHbar !== undefined) mirror.addAccount(OPERATOR, { balance: o.operatorHbar });
    if (o.usdcDecimals !== undefined) mirror.tokens.set(USDC, { token: USDC, symbol: "USDC", name: "USD Coin", decimals: o.usdcDecimals, type: "FUNGIBLE_COMMON" });
    const fac = new FakeFacilitator(mirror);
    fac.down = o.facDown ?? false;
    const cfg = loadConfig({ HEDERA_OPERATOR_ID: OPERATOR, HEDERA_AGENT_ID: AGENT, HEDERA_TOPIC_ID: TOPIC }, ".").hedera;
    const lines: string[] = [];
    const svc = new HederaService({
      cfg,
      priceC: 10,
      payProblems: o.payProblems ?? [],
      recordProblems: o.recordProblems ?? [],
      store: null,
      mirror,
      hedera: null,
      facilitators: new Facilitators([fac], "hedera:testnet"),
      agent: {} as never,
      recorder: {} as never,
      resource: {} as never,
      log: (l) => lines.push(l),
    });
    return { svc, mirror, lines };
  }

  it("before the first probe everything is off", () => {
    assert.deepEqual(service().svc.health(), { hedera: "off", hedera_pay: false, hedera_record: false });
  });

  it("all up: hedera ok, pay and record on", async () => {
    const { svc, lines } = service();
    await svc.probe();
    assert.deepEqual(svc.health(), { hedera: "ok", hedera_pay: true, hedera_record: true });
    assert.ok(lines.some((l) => l.startsWith("hedera: mirror reachable") && l.includes("agent 20.00 USDC")));
  });

  it("the agent holds less than one price of USDC (or none): hedera_pay false", async () => {
    for (const agentUsdc of [99_999n, null]) {
      const { svc } = service({ agentUsdc });
      await svc.probe();
      assert.equal(svc.health().hedera_pay, false);
      assert.equal(svc.health().hedera, "ok");
    }
  });

  it("the facilitator is down: hedera off, hedera_pay false, new buys refused", async () => {
    const { svc } = service({ facDown: true });
    await svc.probe();
    assert.deepEqual(svc.health(), { hedera: "off", hedera_pay: false, hedera_record: true });
    assert.equal(svc.payGate(), "hedera_unavailable");
  });

  it("the mirror is down: hedera off", async () => {
    const { svc, mirror } = service();
    mirror.down = true;
    await svc.probe();
    assert.equal(svc.health().hedera, "off");
  });

  it("the operator holds no HBAR: hedera_record false", async () => {
    const { svc } = service({ operatorHbar: 0n });
    await svc.probe();
    assert.equal(svc.health().hedera_record, false);
  });

  it("incomplete config: pay or record false, gates say not configured", async () => {
    const { svc } = service({ payProblems: ["HEDERA_AGENT_KEY"], recordProblems: ["HEDERA_TOPIC_ID"] });
    await svc.probe();
    assert.equal(svc.health().hedera_pay, false);
    assert.equal(svc.health().hedera_record, false);
    assert.equal(svc.payGate(), "hedera_not_configured");
    assert.equal(svc.paywallGate(), "hedera_not_configured");
    assert.equal(svc.recordGate(), "hedera_not_configured");
  });

  it("HEDERA_USDC that is not a 6-decimal USDC on the mirror: payments off", async () => {
    const { svc, lines } = service({ usdcDecimals: 8 });
    await svc.probe();
    assert.equal(svc.health().hedera_pay, false);
    assert.equal(svc.payGate(), "hedera_unavailable");
    assert.ok(lines.some((l) => l.includes("is not a 6-decimal USDC token")));
  });
});

describe("the Hedera routes", () => {
  async function setup() {
    const h = await hedera();
    open.push(h);
    await h.svc.probe();
    return h;
  }
  const get = async (base: string, path: string) => {
    const res = await fetch(`${base}${path}`);
    return { status: res.status, json: (await res.json()) as any };
  };

  it("GET /health carries hedera, hedera_pay and hedera_record next to the World fields", async () => {
    const h = await setup();
    const r = await get(h.base, "/health");
    assert.deepEqual(r.json, { world: "off", idkit: false, agentpass: false, approvals: null, hedera: "ok", hedera_pay: true, hedera_record: true });
  });

  it("GET /hedera/config: the public ids, caps and the paywall's URL; no key", async () => {
    const h = await setup();
    const r = await get(h.base, "/hedera/config");
    assert.equal(r.status, 200);
    assert.deepEqual(r.json, {
      network: "hedera:testnet",
      mirror: "https://testnet.mirrornode.hedera.com",
      hashscan: "https://hashscan.io/testnet",
      topic: TOPIC,
      usdc: USDC,
      agent: AGENT,
      facilitator: "https://facilitator.test",
      fee_payer: "0.0.9185802",
      caps: { max_c: 10, book_day_c: 100, agent_day_c: 500 },
      resource: `${h.base}/x402/ghost/{listing}`,
    });
    assert.ok(!/key|secret/i.test(Object.keys(r.json).join(",")));
  });

  it("GET /hedera/payto/{book}: the registered account, or null; a bad book is 400", async () => {
    const h = await setup();
    assert.deepEqual((await get(h.base, `/hedera/payto/${h.seller.book}`)).json, { book: h.seller.book, pay_to: SELLER_ACCT });
    assert.deepEqual((await get(h.base, `/hedera/payto/${h.buyer.book}`)).json, { book: h.buyer.book, pay_to: null });
    assert.deepEqual(await get(h.base, "/hedera/payto/nope"), { status: 400, json: { error: "bad_body", failure: "ls_record_fail" } });
  });

  it("GET /hedera/sales/{book}?after=n: the seller's settled sales, oldest first", async () => {
    const h = await setup();
    const { id } = h.agent.start(h.body());
    for (let i = 0; i < 2000 && h.agent.view(id)?.stage !== "done"; i++) await new Promise((r) => setTimeout(r, 5));
    const view = h.agent.view(id)!;
    assert.equal(view.ok, true);
    const r = await get(h.base, `/hedera/sales/${h.seller.book}`);
    assert.deepEqual(r.json, { sales: [{ n: 1, buyer: h.buyer.book, game: "MDGP", amount: "0.10", tx: view.data.receipt }] });
    assert.deepEqual((await get(h.base, `/hedera/sales/${h.seller.book}?after=1`)).json, { sales: [] });
    assert.equal((await get(h.base, `/hedera/sales/${h.seller.book}?after=x`)).status, 400);
  });

  it("not configured: every Hedera route answers 503 with its step's failure; /x402 503", async () => {
    const server = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const post = (path: string) => fetch(`${base}${path}`, { method: "POST", body: "{}" }).then(async (r) => ({ status: r.status, json: await r.json() }));
      assert.deepEqual(await post("/hedera/record"), { status: 503, json: { error: "hedera_not_configured", failure: "ls_record_fail" } });
      assert.deepEqual(await post("/hedera/buy"), { status: 503, json: { error: "hedera_not_configured", failure: "buy_down" } });
      assert.deepEqual(await get(base, "/hedera/config"), { status: 503, json: { error: "hedera_not_configured", failure: "buy_down" } });
      assert.deepEqual(await get(base, "/hedera/buy/p-12345678"), { status: 404, json: { error: "unknown_id", failure: "buy_down" } });
      assert.deepEqual(await get(base, `/x402/ghost/0x${"ab".repeat(32)}`), { status: 503, json: { error: "hedera_not_configured" } });
      assert.equal((await get(base, "/hedera/nope")).status, 404);
    } finally {
      server.close();
    }
  });

  it("the access log has route shapes only: no ids, books, listings or payment headers", async () => {
    const h = await setup();
    await fetch(`${h.base}/hedera/buy`, { method: "POST", body: JSON.stringify(h.body()) });
    await fetch(`${h.base}/x402/ghost/${h.listing}`, { method: "OPTIONS" });
    const access = h.lines.filter((l) => /^(POST|OPTIONS|GET) \//.test(l));
    assert.ok(access.includes(access.find((l) => l.startsWith("POST /hedera/buy 200")) as string));
    assert.ok(access.some((l) => l.startsWith("OPTIONS /x402/ghost/:listing 204")));
    for (const l of access) assert.ok(!l.includes(h.listing) && !l.includes(h.buyer.book), l);
  });
});
