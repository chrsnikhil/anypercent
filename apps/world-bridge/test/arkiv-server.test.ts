/** The Arkiv routes over HTTP: shapes, body limits, errors, /health's fields, the board pages. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";
import { join } from "node:path";
import { after, before, describe, it } from "node:test";
import { MockPayments } from "../src/arkiv/payments.js";
import { actionText, Publisher } from "../src/arkiv/publish.js";
import { ArkivService } from "../src/arkiv/service.js";
import { nullifierKey } from "../src/hmac.js";
import { buildServer, makeHealth } from "../src/server.js";
import { Store } from "../src/store.js";
import { CHECKER, FakeArkiv, FakeChecker, makeLog } from "./fake-arkiv.js";
import { SECRET, tempDir } from "./helpers.js";

const GHOST = "ef".repeat(32);
const DAY = 86_400_000;
const TEXT = actionText("MARINE DRIVE GP", 6170, 10);
const sha = (s: string) => createHash("sha256").update(s).digest("hex");

let server: Server;
let base = "";
let arkiv: FakeArkiv;
let svc: ArkivService;
let store: Store;
let book = "";
const lines: string[] = [];
const dir = tempDir();

function makeService(over: Partial<ConstructorParameters<typeof ArkivService>[0]> = {}) {
  const publisher = new Publisher({ arkiv, checker: new FakeChecker(6170), store, season: 1, runExpiry: new Date(Date.now() + 60 * DAY), priceC: 10, ghostSecret: GHOST, gate: () => svc.gate() });
  return new ArkivService({
    publicRpc: "https://rpc.rabdi.db-chain.testnet.arkiv.network",
    chainId: 7794095,
    season: 1,
    priceC: 10,
    checker: CHECKER,
    arkiv,
    publisher,
    payments: new MockPayments(true, store),
    ghostSecret: GHOST,
    problems: [],
    boardFile: join(dir, "board.html"),
    snapshotFile: join(dir, "snapshot.json"),
    log: (l) => lines.push(l),
    ...over,
  });
}

before(async () => {
  arkiv = new FakeArkiv();
  store = new Store(tempDir(), SECRET);
  book = store.claimBook(nullifierKey(SECRET, "a", "n-srv"), "Orb", "0123456789abcdef", 1, "session_s").record.book;
  svc = makeService();
  await svc.probe();
  writeFileSync(join(dir, "board.html"), "<!doctype html><title>board</title>");
  writeFileSync(join(dir, "snapshot.json"), '{"block": 7}');
  server = buildServer({
    health: () => ({ ...makeHealth(null, null, false), ...svc.health() }),
    idkit: null,
    approvals: null,
    arkiv: svc,
    log: (l) => lines.push(l),
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

after(() => server.close());

async function call(method: string, path: string, body?: unknown, raw?: string) {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: raw ?? (body === undefined ? undefined : JSON.stringify(body)),
  });
  const type = res.headers.get("content-type") ?? "";
  return { status: res.status, type, json: type.startsWith("application/json") ? ((await res.json()) as Record<string, any>) : await res.text() } as {
    status: number;
    type: string;
    json: any;
  };
}

function body(over: Record<string, unknown> = {}) {
  return { book, jti: "srv-jti-1", action: TEXT, game: "MDGP", title: "MARINE DRIVE GP", frames: 6170, price_c: 10, log: Buffer.from(makeLog()).toString("base64"), ...over };
}

describe("GET /health with Arkiv", () => {
  it("adds arkiv, arkiv_writes and checker; the World fields are unchanged", async () => {
    const h = (await call("GET", "/health")).json;
    assert.deepEqual(h, { world: "off", idkit: false, agentpass: false, approvals: null, arkiv: "ok", arkiv_writes: true, checker: CHECKER });
  });

  it("arkiv_writes: false when the chain id differs, the checker is empty, the config is incomplete or Arkiv is down", async () => {
    const a2 = new FakeArkiv();
    const s2 = new ArkivService({ ...svcOptions(), arkiv: a2 });
    await s2.probe();
    assert.deepEqual(s2.health(), { arkiv: "ok", arkiv_writes: true, checker: CHECKER });
    a2.chain = 1;
    await s2.probe();
    assert.deepEqual(s2.health(), { arkiv: "off", arkiv_writes: false, checker: CHECKER });
    assert.equal(s2.gate(), "arkiv_unavailable");
    a2.chain = 7794095;
    a2.balances.clear();
    await s2.probe();
    assert.deepEqual(s2.health(), { arkiv: "ok", arkiv_writes: false, checker: CHECKER });
    assert.equal(s2.gate(), "arkiv_unavailable");
    a2.readsDown = true;
    await s2.probe();
    assert.equal(s2.health().arkiv, "off");
    const s3 = new ArkivService({ ...svcOptions(), problems: ["ARKIV_SEASON_END"] });
    await s3.probe();
    assert.equal(s3.health().arkiv_writes, false);
    assert.equal(s3.gate(), "arkiv_not_configured");
    const s4 = new ArkivService({ ...svcOptions(), checker: null, arkiv: null, publisher: null, problems: ["ARKIV_CHECKER_KEY"] });
    assert.deepEqual(s4.health(), { arkiv: "off", arkiv_writes: false, checker: null });
  });
});

function svcOptions(): ConstructorParameters<typeof ArkivService>[0] {
  return {
    publicRpc: "https://rpc.rabdi.db-chain.testnet.arkiv.network",
    chainId: 7794095,
    season: 1,
    priceC: 10,
    checker: CHECKER,
    arkiv,
    publisher: new Publisher({ arkiv, checker: new FakeChecker(), store, season: 1, runExpiry: new Date(Date.now() + DAY), priceC: 10, ghostSecret: GHOST }),
    payments: new MockPayments(true, store),
    ghostSecret: GHOST,
    problems: [],
    boardFile: "",
    snapshotFile: "",
  };
}

describe("GET /arkiv/config", () => {
  it("answers exactly the contract's fields, never the access key", async () => {
    const r = await call("GET", "/arkiv/config");
    assert.equal(r.status, 200);
    assert.deepEqual(r.json, {
      chain_id: 7794095,
      rpc: "https://rpc.rabdi.db-chain.testnet.arkiv.network",
      explorer: "https://rabdi.explorer.arkiv.network",
      checker: CHECKER,
      season: 1,
      schemas: { run: "anypercent.run", listing: "anypercent.listing" },
      price: "0.10",
      listing_days: 7,
      split_columns: ["s1", "s2", "s3", "s4"],
      explorer_tx: "https://rabdi.explorer.arkiv.network/tx/{tx}",
      explorer_entity: "https://rabdi.explorer.arkiv.network/entity/{key}",
    });
  });
});

describe("POST /arkiv/publish and GET /arkiv/publish/{id}", () => {
  it("200 {id, expires_s: 120}; the job runs to done with {run, listing, tx}; a repeat answers the same id", async () => {
    store.recordApproval("srv-jti-1", book, sha(TEXT), Math.floor(Date.now() / 1000));
    const s = await call("POST", "/arkiv/publish", body());
    assert.equal(s.status, 200);
    assert.deepEqual(Object.keys(s.json).sort(), ["expires_s", "id"]);
    assert.equal(s.json.expires_s, 120);
    assert.match(s.json.id, /^[A-Za-z0-9_-]{16,}$/);
    let v: any;
    for (let i = 0; i < 300; i++) {
      v = (await call("GET", `/arkiv/publish/${s.json.id}`)).json;
      if (v.stage === "done") break;
      await new Promise((r) => setTimeout(r, 5));
    }
    assert.deepEqual(Object.keys(v).sort(), ["data", "failure", "ok", "stage"]);
    assert.equal(v.ok, true);
    assert.deepEqual(Object.keys(v.data).sort(), ["listing", "replay", "run", "tx"]);
    assert.match(v.data.run, /^0x[0-9a-f]{64}$/);
    assert.equal((await call("POST", "/arkiv/publish", body())).json.id, s.json.id);
  });

  it("a job's failure is one of the handler's names", async () => {
    const s = await call("POST", "/arkiv/publish", body({ jti: "never-approved" }));
    let v: any;
    for (let i = 0; i < 300; i++) {
      v = (await call("GET", `/arkiv/publish/${s.json.id}`)).json;
      if (v.stage === "done") break;
      await new Promise((r) => setTimeout(r, 5));
    }
    assert.deepEqual(v, { stage: "done", ok: false, failure: "ls_expired", data: {} });
  });

  it("400 bad_body (ls_publish_fail) on a bad body or bad JSON; 404 unknown_id", async () => {
    for (const r of [await call("POST", "/arkiv/publish", body({ game: "NOPE" })), await call("POST", "/arkiv/publish", undefined, "not json")]) {
      assert.equal(r.status, 400);
      assert.deepEqual(r.json, { error: "bad_body", failure: "ls_publish_fail" });
    }
    const u = await call("GET", "/arkiv/publish/nope");
    assert.equal(u.status, 404);
    assert.deepEqual(u.json, { error: "unknown_id", failure: "ls_publish_fail" });
  });

  it("body limit: up to 192 KiB on /arkiv/publish (a 40 KiB log goes through); over it is 400", async () => {
    store.recordApproval("big-jti", book, sha(TEXT), Math.floor(Date.now() / 1000));
    const big = Buffer.from(makeLog("MDGP", 4, 6461, 40 * 1024)).toString("base64");
    const ok = await call("POST", "/arkiv/publish", body({ jti: "big-jti", log: big }));
    assert.equal(ok.status, 200, JSON.stringify(ok.json));
    const huge = await call("POST", "/arkiv/publish", undefined, JSON.stringify({ ...body(), pad: "x".repeat(193 * 1024) }));
    assert.equal(huge.status, 400);
    assert.deepEqual(huge.json, { error: "bad_body", failure: "ls_publish_fail" });
  });

  it("every other route keeps the 4 KiB limit", async () => {
    const g = await call("POST", "/arkiv/ghost", { run: `0x${"a".repeat(64)}`, receipt: "mock-1a2b3c4d", pad: "x".repeat(5000) });
    assert.equal(g.status, 400);
    assert.deepEqual(g.json, { error: "bad_body", failure: "buy_load_fail" });
    const a = await call("POST", "/agentpass/start", { book: "ANY-ABC", action: "x", pad: "x".repeat(5000) });
    assert.equal(a.status, 413, "the World routes are unchanged");
  });

  it("503 arkiv_not_configured when the config is incomplete", async () => {
    const bare = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null, arkiv: new ArkivService({ ...svcOptions(), problems: ["ARKIV_CHECKER_KEY"], publisher: null }) });
    await new Promise<void>((r) => bare.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${(bare.address() as AddressInfo).port}`;
    const r = await fetch(`${url}/arkiv/publish`, { method: "POST", body: JSON.stringify(body()) });
    assert.equal(r.status, 503);
    assert.deepEqual(await r.json(), { error: "arkiv_not_configured", failure: "ls_publish_fail" });
    bare.close();
  });

  it("with no Arkiv module at all: 503 on publish and config, 404 on the board", async () => {
    const bare = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null });
    await new Promise<void>((r) => bare.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${(bare.address() as AddressInfo).port}`;
    assert.equal((await fetch(`${url}/arkiv/publish`, { method: "POST", body: JSON.stringify(body()) })).status, 503);
    assert.equal((await fetch(`${url}/arkiv/config`)).status, 503);
    const g = await fetch(`${url}/arkiv/ghost`, { method: "POST", body: JSON.stringify({ run: `0x${"a".repeat(64)}`, receipt: "mock-1a2b3c4d" }) });
    assert.deepEqual([g.status, await g.json()], [503, { error: "arkiv_not_configured", failure: "buy_load_fail" }]);
    assert.equal((await fetch(`${url}/board`)).status, 404);
    bare.close();
  });
});

describe("POST /arkiv/ghost over HTTP", () => {
  it("200 {log, log_h} for a listed run with a mock receipt; 402 for a reused receipt; 404 not_on_board", async () => {
    const { encryptGhost, sha256Hex } = await import("../src/arkiv/ghost.js");
    const log = makeLog("MDGP", 4, 6461, 64, 77);
    const logH = sha256Hex(log);
    const run = arkiv.addRun({ game: "MDGP", title: "M", season: 1, rules: 4, frames: 6170, log_h: logH, runner: "r", book, human: true, tool: "t", log_enc: encryptGhost(GHOST, logH, log) });
    const ok = await call("POST", "/arkiv/ghost", { run, receipt: "mock-0badf00d" });
    assert.equal(ok.status, 200);
    assert.deepEqual(ok.json, { log: Buffer.from(log).toString("base64"), log_h: logH });
    const other = arkiv.addRun({ game: "MDGP", title: "M", season: 1, rules: 4, frames: 6170, log_h: logH, runner: "r", book, human: true, tool: "t", log_enc: encryptGhost(GHOST, logH, log) });
    const reused = await call("POST", "/arkiv/ghost", { run: other, receipt: "mock-0badf00d" });
    assert.deepEqual([reused.status, reused.json], [402, { error: "payment_required", failure: "buy_load_fail" }]);
    const none = await call("POST", "/arkiv/ghost", { run: `0x${"7".repeat(64)}`, receipt: "mock-0badf00e" });
    assert.deepEqual([none.status, none.json], [404, { error: "not_on_board", failure: "buy_load_fail" }]);
  });
});

describe("the web board", () => {
  it("GET /board serves the page, GET /board/snapshot.json the snapshot", async () => {
    const page = await call("GET", "/board");
    assert.equal(page.status, 200);
    assert.match(page.type, /^text\/html/);
    assert.match(page.json, /<title>board<\/title>/);
    const snap = await call("GET", "/board/snapshot.json");
    assert.equal(snap.status, 200);
    assert.deepEqual(snap.json, { block: 7 });
  });
});

describe("the access log", () => {
  it("has route shapes only (/arkiv/publish/:id) and never a jti, a log or a secret", async () => {
    await call("POST", "/arkiv/publish/abc", {});
    const all = lines.join("\n");
    assert.match(all, /POST \/arkiv\/publish 200/);
    assert.match(all, /POST \/arkiv\/publish\/:id 404/);
    for (const bad of ["srv-jti-1", "big-jti", GHOST, SECRET, Buffer.from(makeLog()).toString("base64").slice(0, 40)]) {
      assert.ok(!all.includes(bad), `leaked ${bad.slice(0, 6)}`);
    }
  });
});
