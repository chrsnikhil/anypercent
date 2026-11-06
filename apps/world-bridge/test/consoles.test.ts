/**
 * One console, one person: tags, registration, the binding at sign-up (and id_taken before the
 * portal), the owner's link and release on a World approval with exact texts, approvals spent on an
 * op refused by publish and record, and the HTTP routes and their log shapes.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import type { AddressInfo } from "node:net";
import { afterEach, describe, it } from "node:test";
import { Consoles, consoleKey, CONSOLE_TAG_RE, linkText, releaseText, tagCandidate, type OpView } from "../src/consoles.js";
import { actionText, Publisher } from "../src/arkiv/publish.js";
import { nullifierKey } from "../src/hmac.js";
import { IdkitSessions } from "../src/idkit.js";
import { Nullifier } from "@worldcoin/idkit-core/nullifier";
import { buildServer, makeHealth } from "../src/server.js";
import { Store } from "../src/store.js";
import { FakeApprovals } from "./fake-approvals.js";
import { FakeArkiv, FakeChecker, makeLog } from "./fake-arkiv.js";
import { ACTION, confirmed, FakeWorld, portalOk, proof } from "./fake-world.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const PI = "a1b2c3d4e5f60718293a4b5c6d7e8f90"; // a console id, as console_id.py makes them
const LAPTOP = "ffeeddccbbaa99887766554433221100";
const sha = (s: string) => createHash("sha256").update(s).digest("hex");

let live: Array<{ stopAll(): void }> = [];
afterEach(() => {
  for (const s of live) s.stopAll();
  live = [];
});

function setup() {
  const store = new Store(tempDir(), SECRET);
  const lines: string[] = [];
  const approvals = new FakeApprovals(store);
  const consoles = new Consoles({ store, secret: SECRET, approvals, pollMs: 2, log: (l) => lines.push(l) });
  live.push(consoles);
  return { store, lines, approvals, consoles };
}

function signups(s: ReturnType<typeof setup>, world: FakeWorld) {
  const idkit = new IdkitSessions({ deps: world, store: s.store, secret: SECRET, action: ACTION, environment: "staging", pollMs: 2, consoles: s.consoles, log: (l) => s.lines.push(l) });
  live.push(idkit);
  return async (consoleId: string) => {
    const { id } = await idkit.start(consoleId);
    await waitFor(() => idkit.view(id)?.stage === "done");
    return idkit.view(id)!;
  };
}

async function op(c: Consoles, body: Record<string, unknown>): Promise<OpView> {
  const { id } = await c.startOp(body);
  assert.match(id, /^o-[0-9a-f]{8}$/);
  await waitFor(() => c.opView(id)?.stage === "done");
  return c.opView(id)!;
}

describe("console ids, keys and tags", () => {
  it("the key is an HMAC of the id; tags are C- plus 4 book characters, stable and unique", () => {
    const s = setup();
    assert.match(consoleKey(SECRET, PI), /^[0-9a-f]{64}$/);
    assert.notEqual(consoleKey(SECRET, PI), consoleKey("another-secret-0123456789abcdef-xyz", PI));
    const a = s.consoles.view(PI);
    assert.match(a.tag, CONSOLE_TAG_RE);
    assert.deepEqual(s.consoles.view(PI), a, "stable");
    assert.notEqual(s.consoles.view(LAPTOP).tag, a.tag);
    assert.equal(tagCandidate(SECRET, consoleKey(SECRET, PI), 0), a.tag);
  });

  it("GET registers an unseen console as unbound, and the raw id is never stored or logged", () => {
    const s = setup();
    assert.deepEqual({ ...s.consoles.view(PI), tag: "x" }, { tag: "x", book: null, state: "unbound", credential: null, wallet: null, wallet_pending: false });
    assert.ok(s.store.consoleFor(consoleKey(SECRET, PI)));
    const state = JSON.stringify((s.store as unknown as { state: unknown }).state);
    assert.ok(!state.includes(PI), "no raw console id on disk");
    assert.ok(!s.lines.join("\n").includes(PI), "no raw console id in the log");
  });

  it("refuses an id that is not a console id", () => {
    const s = setup();
    assert.throws(() => s.consoles.view("pi-booth"));
    assert.equal(s.consoles.boundTo("pi-booth"), null);
  });

  it("two consoles never share a tag, even when a candidate collides", () => {
    const s = setup();
    const tags = new Set<string>();
    for (let i = 0; i < 200; i++) tags.add(s.consoles.view(`console-${String(i).padStart(12, "0")}`).tag);
    assert.equal(tags.size, 200);
  });
});

describe("the binding at sign-up", () => {
  it("a sign-up on an unbound console binds it, and data gains the console's tag", async () => {
    const s = setup();
    const signup = signups(s, new FakeWorld((signal) => [confirmed(proof(signal, "0x0a01"))]));
    const v = await signup(PI);
    assert.equal(v.ok, true);
    const tag = s.consoles.view(PI).tag;
    assert.equal(v.data.console, tag);
    assert.deepEqual(s.consoles.view(PI), { tag, book: v.data.book, state: "bound", credential: "Selfie Check", wallet: null, wallet_pending: false });
    assert.equal(s.store.consoleFor(consoleKey(SECRET, PI))?.by, "signup");
  });

  it("an older launcher's host name binds nothing (as before consoles)", async () => {
    const s = setup();
    const signup = signups(s, new FakeWorld((signal) => [confirmed(proof(signal, "0x0a02"))]));
    const v = await signup("pi-booth");
    assert.equal(v.ok, true);
    assert.deepEqual(Object.keys(v.data).sort(), ["book", "credential", "runner_id"]);
  });

  it("id_dup that names the book binds an unbound console to it (sign-in)", async () => {
    const s = setup();
    const signup = signups(s, new FakeWorld((signal) => [confirmed(proof(signal, "0x0a03"))]));
    const first = await signup(LAPTOP);
    const again = await signup(PI);
    assert.equal(again.failure, "id_dup");
    assert.equal(again.data.book, first.data.book);
    assert.equal(s.consoles.view(PI).book, first.data.book);
    assert.equal(s.store.consoleFor(consoleKey(SECRET, PI))?.by, "signin");
  });

  it("another person's proof on a bound console: id_taken before the portal; no verify call, no book, nothing stored", async () => {
    const s = setup();
    let n = 0;
    const world = new FakeWorld((signal) => [confirmed(proof(signal, n++ === 0 ? "0x0b01" : "0x0b02"))], () => portalOk());
    const signup = signups(s, world);
    const owner = await signup(PI);
    const tag = s.consoles.view(PI).tag;
    const verifiedBefore = world.verified.length;
    const booksBefore = JSON.stringify((s.store as unknown as { state: { books: unknown } }).state.books);
    const taken = await signup(PI);
    assert.equal(taken.ok, false);
    assert.equal(taken.failure, "id_taken");
    assert.deepEqual(taken.data, { book: owner.data.book, console: tag });
    assert.equal(world.verified.length, verifiedBefore, "the portal never saw the proof");
    assert.equal(JSON.stringify((s.store as unknown as { state: { books: unknown } }).state.books), booksBefore, "no book made");
    const nKey = nullifierKey(SECRET, ACTION, Nullifier.fromHex("0x0b02").toCanonicalString());
    assert.equal(s.store.bookFor(nKey), undefined);
    assert.ok(s.lines.includes(`idkit sign-up: id_taken (console ${tag} belongs to ${owner.data.book}; not sent to the portal)`), s.lines.join("\n"));
    // On another console the same person signs up as normal.
    const elsewhere = await signup(LAPTOP);
    assert.equal(elsewhere.ok, true);
  });

  it("the owner's repeat on their own bound console reaches the portal and gets id_dup, as before", async () => {
    const s = setup();
    let calls = 0;
    const world = new FakeWorld(
      (signal) => [confirmed(proof(signal, "0x0c01"))],
      () => (calls++ === 0 ? portalOk() : { status: 400, body: { success: false, code: "all_verifications_failed", results: [{ code: "max_verifications_reached" }] } }),
    );
    const signup = signups(s, world);
    const first = await signup(PI);
    const again = await signup(PI);
    assert.equal(again.failure, "id_dup");
    assert.deepEqual(again.data, { book: first.data.book });
    assert.equal(world.verified.length, 2);
  });
});

describe("link and release: owner ops on one World approval each", () => {
  async function bookOn(s: ReturnType<typeof setup>, consoleId: string, nullifier: string) {
    const signup = signups(s, new FakeWorld((signal) => [confirmed(proof(signal, nullifier))]));
    return String((await signup(consoleId)).data.book);
  }

  it("release, then GET, then link back: the exact texts, World approval each time, approvals spent on the op", async () => {
    const s = setup();
    const book = await bookOn(s, PI, "0x0d01");
    const tag = s.consoles.view(PI).tag;
    const started = await s.consoles.startOp({ op: "release", console: tag });
    assert.equal(started.action, `Release console ${tag} from record book ${book}`);
    assert.equal(started.action, releaseText(tag, book));
    assert.deepEqual(Object.keys(started.approval).sort(), ["code", "expires_s", "id", "qr"]);
    assert.deepEqual(s.approvals.started.at(-1), { id: started.approval.id, book, action: started.action, cancelled: false });
    await waitFor(() => s.consoles.opView(started.id)?.stage === "done");
    assert.deepEqual(s.consoles.opView(started.id), { stage: "done", ok: true, failure: null, data: { tag, book: null, state: "released" } });
    assert.deepEqual(s.consoles.view(PI), { tag, book: null, state: "released", credential: null, wallet: null, wallet_pending: false });
    assert.equal(s.store.approvalFor(`jti-${started.approval.id}`)?.used_for, `console-release:${tag}`);

    const link = await s.consoles.startOp({ op: "link", console: tag, book });
    assert.equal(link.action, `Link console ${tag} to record book ${book}: PB on it spends this book's coach budget`);
    assert.equal(link.action, linkText(tag, book));
    await waitFor(() => s.consoles.opView(link.id)?.stage === "done");
    assert.equal(s.consoles.opView(link.id)?.ok, true);
    assert.deepEqual(s.consoles.view(PI).state, "bound");
    assert.equal(s.store.consoleFor(consoleKey(SECRET, PI))?.by, "link");
  });

  it("refusals before any approval: unknown console 404, link on a bound console 409, release of an unbound one 409, bad bodies 400", async () => {
    const s = setup();
    const book = await bookOn(s, PI, "0x0d02");
    const tag = s.consoles.view(PI).tag;
    const other = s.consoles.view(LAPTOP).tag;
    const refused = async (body: Record<string, unknown>) => {
      try {
        await s.consoles.startOp(body);
        return "started";
      } catch (e) {
        return `${(e as { status: number }).status} ${(e as Error).message}`;
      }
    };
    assert.equal(await refused({ op: "link", console: "C-2222", book }), "404 unknown_console");
    assert.equal(await refused({ op: "link", console: tag, book }), "409 already_bound");
    assert.equal(await refused({ op: "release", console: other }), "409 not_bound");
    assert.equal(await refused({ op: "release", console: tag, book: "ANY-ZZZ" }), "409 not_bound");
    assert.equal(await refused({ op: "link", console: other, book: "ANY-ZZZ" }), "404 unknown_book");
    assert.equal(await refused({ op: "link", console: other }), "400 bad_body");
    assert.equal(await refused({ op: "wipe", console: tag }), "400 bad_body");
    assert.equal(await refused({ op: "link", console: "pi-booth", book }), "400 bad_body");
    assert.equal(s.approvals.started.length, 0, "no approval was started for any of them");
  });

  it("an approval recorded for another book: ls_wrong, nothing changes", async () => {
    const s = setup();
    const book = await bookOn(s, PI, "0x0d03");
    const tag = s.consoles.view(PI).tag;
    s.approvals.recordAs = "ANY-ZZZ";
    const v = await op(s.consoles, { op: "release", console: tag });
    assert.deepEqual([v.ok, v.failure], [false, "ls_wrong"]);
    assert.equal(s.consoles.view(PI).book, book);
  });

  it("an approval already spent on a listing, or on another op: ls_reused", async () => {
    const s = setup();
    await bookOn(s, PI, "0x0d04");
    const tag = s.consoles.view(PI).tag;
    const book = String(s.consoles.view(PI).book);
    // A listing approval for this very text, already spent on a log.
    s.store.recordApproval("jti-spent", book, sha(releaseText(tag, book)), Math.floor(Date.now() / 1000));
    s.store.spendApproval("jti-spent", "e".repeat(64));
    s.approvals.reuseJti = "jti-spent";
    assert.equal((await op(s.consoles, { op: "release", console: tag })).failure, "ls_reused");
    // One spent on another op.
    s.store.recordApproval("jti-op", book, sha(releaseText(tag, book)), Math.floor(Date.now() / 1000));
    s.store.spendApprovalFor("jti-op", "house:abcdef");
    s.approvals.reuseJti = "jti-op";
    assert.equal((await op(s.consoles, { op: "release", console: tag })).failure, "ls_reused");
    assert.equal(s.consoles.view(PI).state, "bound");
  });

  it("World App's refusal is the op's failure; Ctrl-C cancels the approval and nothing changes", async () => {
    const s = setup();
    await bookOn(s, PI, "0x0d05");
    const tag = s.consoles.view(PI).tag;
    s.approvals.outcome = "ls_denied";
    assert.equal((await op(s.consoles, { op: "release", console: tag })).failure, "ls_denied");
    s.approvals.outcome = null;
    s.approvals.hold = true;
    const { id, approval } = await s.consoles.startOp({ op: "release", console: tag });
    assert.equal(s.consoles.cancelOp(id), true);
    assert.equal(s.consoles.opView(id)?.failure, "ls_denied");
    assert.equal(s.approvals.started.find((a) => a.id === approval.id)?.cancelled, true);
    assert.equal(s.consoles.cancelOp("o-00000000"), false);
    assert.equal(s.consoles.view(PI).state, "bound");
  });

  it("spending follows the binding", async () => {
    const s = setup();
    const book = await bookOn(s, PI, "0x0d06");
    assert.equal(s.consoles.canSpend(PI, book).ok, true);
    assert.equal(s.consoles.canSpend(PI, "ANY-ZZZ").ok, false);
    assert.equal(s.consoles.canSpend(LAPTOP, book).ok, false, "an unbound console spends from no book");
    assert.equal(s.consoles.canSpend("pi-booth", book).ok, false);
  });
});

describe("an approval spent on an op is refused by publish and record", () => {
  it("publish answers ls_reused for an approval used for a console op", async () => {
    const store = new Store(tempDir(), SECRET);
    const rec = store.claimBook(nullifierKey(SECRET, "a", "op-pub"), "Orb", "0123456789abcdef", 1, "session_p").record;
    const text = actionText("MARINE DRIVE GP", 6170, 10);
    store.recordApproval("jti-op-pub", rec.book, sha(text), Math.floor(Date.now() / 1000));
    store.spendApprovalFor("jti-op-pub", "console-link:C-7QZP");
    assert.equal(store.spendApproval("jti-op-pub", "a".repeat(64)), "other");
    const pub = new Publisher({ arkiv: new FakeArkiv(), checker: new FakeChecker(6170), store, season: 1, runExpiry: new Date(Date.now() + 864e5 * 60), priceC: 10, ghostSecret: "ab".repeat(32), chainId: 7794095, rpc: "https://rpc.example" });
    const { id } = pub.start({ book: rec.book, jti: "jti-op-pub", action: text, game: "MDGP", title: "MARINE DRIVE GP", frames: 6170, price_c: 10, log: Buffer.from(makeLog()).toString("base64") });
    await waitFor(() => pub.view(id)?.stage === "done");
    assert.equal(pub.view(id)?.failure, "ls_reused");
  });

  it("and an approval spent on a listing cannot be spent on an op", () => {
    const store = new Store(tempDir(), SECRET);
    store.recordApproval("jti-l", "ANY-ABC", "0".repeat(64), 1);
    store.spendApproval("jti-l", "a".repeat(64));
    assert.equal(store.spendApprovalFor("jti-l", "console-link:C-7QZP"), "other");
    store.recordApproval("jti-o", "ANY-ABC", "0".repeat(64), 1);
    assert.equal(store.spendApprovalFor("jti-o", "console-link:C-7QZP"), "spent");
    assert.equal(store.spendApprovalFor("jti-o", "console-link:C-7QZP"), "same");
    assert.equal(store.spendApprovalFor("jti-o", "console-release:C-7QZP"), "other");
    assert.equal(store.spendApprovalFor("jti-none", "x"), "unknown");
  });
});

describe("the console routes", () => {
  it("GET /console/{id}, POST /console/op, GET /console/op/{id}, cancel; errors carry id_offline; the log has shapes only", async () => {
    const s = setup();
    const signup = signups(s, new FakeWorld((signal) => [confirmed(proof(signal, "0x0e01"))]));
    const book = String((await signup(PI)).data.book);
    const lines: string[] = [];
    const server = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null, consoles: s.consoles, log: (l) => lines.push(l) });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const call = async (method: string, path: string, body?: unknown) => {
        const r = await fetch(`${base}${path}`, { method, headers: { "content-type": "application/json" }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
        return { status: r.status, json: (await r.json()) as Record<string, any> };
      };
      const g = await call("GET", `/console/${PI}`);
      assert.equal(g.status, 200);
      assert.deepEqual(Object.keys(g.json).sort(), ["book", "credential", "state", "tag", "wallet", "wallet_pending"]);
      assert.equal(g.json.book, book);
      assert.deepEqual(await call("GET", "/console/pi-booth"), { status: 400, json: { error: "bad_console", failure: "id_offline" } });
      const o = await call("POST", "/console/op", { op: "release", console: g.json.tag });
      assert.equal(o.status, 200);
      assert.match(o.json.id, /^o-/);
      assert.equal(o.json.action, releaseText(g.json.tag, book));
      let v: Record<string, any>;
      do v = (await call("GET", `/console/op/${o.json.id}`)).json;
      while (v.stage !== "done");
      assert.deepEqual(v, { stage: "done", ok: true, failure: null, data: { tag: g.json.tag, book: null, state: "released" } });
      assert.deepEqual(await call("POST", "/console/op", { op: "release", console: g.json.tag }), { status: 409, json: { error: "not_bound", failure: "id_offline" } });
      assert.deepEqual(await call("POST", "/console/op/o-00000000/cancel"), { status: 404, json: { error: "unknown_id", failure: "id_offline" } });
      assert.deepEqual(await call("GET", "/console/op/o-00000000"), { status: 404, json: { error: "unknown_id", failure: "id_offline" } });
      assert.ok(lines.includes("POST /console/op 200 " + lines.find((l) => l.startsWith("POST /console/op 200"))!.split(" ").pop()));
      assert.ok(lines.some((l) => l.startsWith("POST /console/op/:id/cancel 404")));
      assert.ok(!lines.join("\n").includes(PI));
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });

  it("without a store the console routes answer 503 id_offline", async () => {
    const server = buildServer({ health: () => makeHealth(null, null, false), idkit: null, approvals: null });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const r = await fetch(`${base}/console/${PI}`);
      assert.deepEqual([r.status, await r.json()], [503, { error: "consoles_not_configured", failure: "id_offline" }]);
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });
});

describe("/health's pivot fields", () => {
  it("console, splits, scout and house, from what is wired", async () => {
    const { pivotHealth } = await import("../src/server.js");
    assert.deepEqual(pivotHealth({ consoles: null, splits: false, scout: null, house: null, arkivWrites: true }), { console: false, splits: false, scout: "off", house: false, house_off: "not configured" });
    assert.deepEqual(pivotHealth({ consoles: {}, splits: true, scout: { mode: () => "model" }, house: {}, arkivWrites: true }), { console: true, splits: true, scout: "model", house: true, house_off: null });
    assert.equal(pivotHealth({ consoles: {}, splits: true, scout: { mode: () => "rule" }, house: {}, arkivWrites: false }).house, false, "house needs Arkiv writes");
  });
});
