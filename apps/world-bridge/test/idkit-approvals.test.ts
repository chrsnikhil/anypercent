import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { afterEach, describe, it } from "node:test";
import { Nullifier } from "@worldcoin/idkit-core/nullifier";
import { StartFailure } from "../src/approvals.js";
import { jtiKey, nullifierKey } from "../src/hmac.js";
import { approvalJti, IdkitApprovals } from "../src/idkit-approvals.js";
import { Store } from "../src/store.js";
import { ACTION, awaiting, confirmed, failed, FakeWorld, proof, waiting } from "./fake-world.js";
import { SECRET, sleep, tempDir, waitFor } from "./helpers.js";

const DIGEST = "list MDGP 1:42.83 ghost at 0.10 USDC";
const OWNER = "0x0abc";
const STRANGER = "0x0def";

/** What the proof-of-human preset returns: a 4.0 Orb item. expires_at_min is the request time. */
const orb = (signal: string, nullifier = OWNER, over: Record<string, unknown> = {}, item: Record<string, unknown> = {}) =>
  proof(signal, nullifier, over, {
    identifier: "proof_of_human",
    issuer_schema_id: 1,
    sybil_score: undefined,
    expires_at_min: Math.floor(Date.now() / 1000) - 20,
    ...item,
  });

const portalOrb = () => ({
  status: 200,
  body: { success: true, action: ACTION, environment: "staging", results: [{ identifier: "proof_of_human", success: true }] },
});

const keyOf = (hex: string) => nullifierKey(SECRET, ACTION, Nullifier.fromHex(hex).toCanonicalString());

/** The record book this nullifier signed up for. */
function own(store: Store, hex: string): string {
  return store.claimBook(keyOf(hex), "Orb", "runner", 1).record.book;
}

let live: IdkitApprovals[] = [];
afterEach(() => {
  for (const a of live) a.stopAll();
  live = [];
});

function make(world: FakeWorld, store = new Store(tempDir(), SECRET), over: Record<string, unknown> = {}) {
  const lines: string[] = [];
  const a = new IdkitApprovals({
    deps: world,
    store,
    secret: SECRET,
    action: ACTION,
    environment: "staging",
    pollMs: 2,
    log: (l: string) => lines.push(l),
    ...over,
  });
  live.push(a);
  return { ap: a, store, lines };
}

async function finish(ap: IdkitApprovals, id: string) {
  await waitFor(() => ap.view(id)?.stage === "done");
  return ap.view(id)!;
}

describe("listing approvals on IDKit", () => {
  it("is the idkit provider", () => {
    assert.equal(make(new FakeWorld(() => [waiting])).ap.kind, "idkit");
  });

  it("start returns the World App link, a display code and the 300 s lifetime", async () => {
    const { ap, store } = make(new FakeWorld(() => [waiting]));
    const s = await ap.start(own(store, OWNER), DIGEST);
    assert.deepEqual(Object.keys(s).sort(), ["code", "expires_s", "id", "qr"]);
    assert.equal(s.qr, "https://staging.world.org/verify?t=fake");
    assert.match(s.code, /^[A-Z2-9]{3}-[A-Z2-9]{3}$/);
    assert.equal(s.expires_s, 300);
    assert.deepEqual(ap.view(s.id), { stage: "scan", ok: null, failure: null, data: {} });
  });

  it("the signal is anyl1|<book>|<sha256(digest)[:16]>|<session id>, never 0x", async () => {
    const world = new FakeWorld(() => [waiting]);
    const { ap, store } = make(world);
    const book = own(store, OWNER);
    const s = await ap.start(book, DIGEST);
    const digest16 = createHash("sha256").update(DIGEST).digest("hex").slice(0, 16);
    assert.equal(world.signals[0], `anyl1|${book}|${digest16}|${s.id}`);
    assert.ok(!world.signals[0].startsWith("0x"));
  });

  it("walks scan -> approve -> done; the owner's proof gives a one-time {jti}", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const world = new FakeWorld((signal) => [waiting, waiting, awaiting, awaiting, confirmed(orb(signal))], portalOrb);
    const realVerify = world.verify.bind(world);
    world.verify = async (p) => {
      await gate;
      return realVerify(p);
    };
    const { ap, store, lines } = make(world);
    const { id } = await ap.start(own(store, OWNER), DIGEST);
    const seen: string[] = [];
    const record = () => {
      const st = ap.view(id)!.stage;
      if (seen[seen.length - 1] !== st) seen.push(st);
    };
    await waitFor(() => (record(), world.verified.length === 0 && seen.includes("approve")));
    assert.deepEqual(ap.view(id), { stage: "approve", ok: null, failure: null, data: {} });
    release();
    await waitFor(() => (record(), ap.view(id)!.stage === "done"));
    assert.deepEqual(seen, ["scan", "approve", "done"]);
    const v = ap.view(id)!;
    assert.equal(v.ok, true);
    assert.equal(v.failure, null);
    assert.deepEqual(Object.keys(v.data), ["jti"]);
    assert.match(String(v.data.jti), /^[0-9a-f]{16}$/);
    assert.equal(v.data.jti, approvalJti(id, keyOf(OWNER)));
    // The log names the outcome but never the jti or the nullifier.
    const all = lines.join("\n");
    assert.match(all, /approved/);
    assert.ok(!all.includes(String(v.data.jti)));
    assert.ok(!all.toLowerCase().includes("0abc"));
  });

  it("forwards the IDKit result to the portal unchanged", async () => {
    let sent: unknown;
    const world = new FakeWorld((signal) => [confirmed((sent = orb(signal)))], portalOrb);
    const { ap, store } = make(world);
    await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id);
    assert.equal(world.verified[0], sent);
  });

  it("a past expires_at_min (the request's lower bound) is fine", async () => {
    const world = new FakeWorld((signal) => [confirmed(orb(signal, OWNER, {}, { expires_at_min: 1000 }))], portalOrb);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).ok, true);
  });

  it("each approval is a fresh one-time id", async () => {
    const world = new FakeWorld((signal) => [confirmed(orb(signal))], portalOrb);
    const { ap, store } = make(world);
    const book = own(store, OWNER);
    const a = await finish(ap, (await ap.start(book, DIGEST)).id);
    const b = await finish(ap, (await ap.start(book, DIGEST)).id);
    assert.equal(a.ok && b.ok, true);
    assert.notEqual(a.data.jti, b.data.jti);
  });

  it("an approval id already used: ls_reused", async () => {
    const world = new FakeWorld((signal) => [waiting, waiting, waiting, confirmed(orb(signal))], portalOrb);
    const { ap, store } = make(world, undefined, { pollMs: 10 });
    const { id } = await ap.start(own(store, OWNER), DIGEST);
    // The same session's proof consumed already (a replay): the store says used.
    assert.equal(store.useJti(jtiKey("idkit-approval", approvalJti(id, keyOf(OWNER))), 1), true);
    assert.equal((await finish(ap, id)).failure, "ls_reused");
  });

  it("a World ID that owns no record book: ls_wrong", async () => {
    const world = new FakeWorld((signal) => [confirmed(orb(signal, STRANGER))], portalOrb);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_wrong");
  });

  it("a World ID that owns ANOTHER record book: ls_wrong", async () => {
    const world = new FakeWorld((signal) => [confirmed(orb(signal, STRANGER))], portalOrb);
    const { ap, store } = make(world);
    const mine = own(store, OWNER);
    own(store, STRANGER);
    assert.equal((await finish(ap, (await ap.start(mine, DIGEST)).id)).failure, "ls_wrong");
  });

  it("a book this bridge never issued: ls_wrong (nobody owns it)", async () => {
    const world = new FakeWorld((signal) => [confirmed(orb(signal))], portalOrb);
    const { ap, store } = make(world);
    own(store, OWNER);
    assert.equal((await finish(ap, (await ap.start("ANY-ZZZ", DIGEST)).id)).failure, "ls_wrong");
  });

  const appFailures: Array<[string, string]> = [
    ["user_rejected", "ls_denied"],
    ["cancelled", "ls_denied"],
    ["timeout", "ls_expired"],
    ["credential_unavailable", "ls_wrong"],
    ["invalid_rp_signature", "ls_world_down"],
    ["connection_failed", "ls_world_down"],
    ["max_verifications_reached", "ls_world_down"],
  ];
  for (const [code, failure] of appFailures) {
    it(`World App answers ${code}: ${failure}`, async () => {
      const { ap, store } = make(new FakeWorld(() => [waiting, awaiting, failed(code)]));
      const v = await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id);
      assert.deepEqual(v, { stage: "done", ok: false, failure, data: {} });
    });
  }

  it("a proof bound to another request (signal): ls_mismatch, portal never asked", async () => {
    const world = new FakeWorld(() => [confirmed(orb("anyl1|ANY-XXX|0000|other"))], portalOrb);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_mismatch");
    assert.equal(world.verified.length, 0);
  });

  it("a record-book sign-up proof replayed as an approval: ls_mismatch", async () => {
    const world = new FakeWorld(() => [confirmed(orb("anyb1|0123456789abcdef|session"))], portalOrb);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_mismatch");
  });

  it("another environment, another action, or a legacy 3.0 proof: ls_mismatch", async () => {
    for (const over of [{ environment: "production" }, { action: "other-action" }, { protocol_version: "3.0" }]) {
      const world = new FakeWorld((signal) => [confirmed(orb(signal, OWNER, over))], portalOrb);
      const { ap, store } = make(world);
      assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_mismatch");
      assert.equal(world.verified.length, 0);
    }
  });

  it("the portal refusing the proof: ls_mismatch", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(orb(signal))],
      () => ({ status: 400, body: { success: false, code: "all_verifications_failed", results: [{ code: "verification_error" }] } }),
    );
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_mismatch");
  });

  it("the portal refusing a repeat (the action is capped): ls_world_down, with a hint in the log", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(orb(signal))],
      () => ({ status: 400, body: { success: false, code: "max_verifications_reached" } }),
    );
    const { ap, store, lines } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_world_down");
    assert.match(lines.join("\n"), /unlimited verifications/);
  });

  it("the portal down, 5xx or unreachable: ls_world_down", async () => {
    for (const portal of [() => new Error("ECONNRESET"), () => ({ status: 502, body: undefined }), () => ({ status: 404, body: {} })]) {
      const world = new FakeWorld((signal) => [confirmed(orb(signal))], portal);
      const { ap, store } = make(world);
      assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_world_down");
    }
  });

  it("a credential we do not accept: ls_wrong", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(orb(signal, OWNER, {}, { identifier: "passport", issuer_schema_id: 9303 }))],
      portalOrb,
    );
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(own(store, OWNER), DIGEST)).id)).failure, "ls_wrong");
  });

  it("World's bridge unreachable for too long: ls_world_down; a blip is survived", async () => {
    const out = make(new FakeWorld(() => [new Error("fetch failed")]), undefined, { networkGraceMs: 30 });
    assert.equal((await finish(out.ap, (await out.ap.start(own(out.store, OWNER), DIGEST)).id)).failure, "ls_world_down");
    const blip = make(new FakeWorld((signal) => [new Error("fetch failed"), confirmed(orb(signal))], portalOrb), undefined, {
      networkGraceMs: 5000,
    });
    assert.equal((await finish(blip.ap, (await blip.ap.start(own(blip.store, OWNER), DIGEST)).id)).ok, true);
  });

  it("no answer within the lifetime: ls_expired", async () => {
    let t = Date.now();
    const { ap, store } = make(new FakeWorld(() => [waiting]), undefined, { now: () => t, ttlS: 1 });
    const { id } = await ap.start(own(store, OWNER), DIGEST);
    t += 7000;
    assert.equal((await finish(ap, id)).failure, "ls_expired");
  });

  it("a request World's bridge will not create: StartFailure(ls_world_down)", async () => {
    const world = new FakeWorld(() => [waiting]);
    world.createFails = true;
    const { ap, store } = make(world);
    await assert.rejects(
      ap.start(own(store, OWNER), DIGEST),
      (e: unknown) => e instanceof StartFailure && e.failure === "ls_world_down" && e.status === 503,
    );
  });
});

describe("IDKit approvals: Circle on the console always wins", () => {
  const cancelled = { stage: "done", ok: false, failure: "ls_denied", data: {} };

  it("cancel answers done / ls_denied at once, idempotently, and stops polling", async () => {
    const world = new FakeWorld((signal) => [awaiting, awaiting, awaiting, awaiting, confirmed(orb(signal))], portalOrb);
    const { ap, store } = make(world, undefined, { pollMs: 5 });
    const { id } = await ap.start(own(store, OWNER), DIGEST);
    await waitFor(() => ap.view(id)!.stage === "approve");
    assert.equal(ap.cancel(id), true);
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(ap.cancel(id), true);
    await sleep(60);
    assert.equal(world.verified.length, 0, "the late Approve never reaches the portal");
    assert.deepEqual(ap.view(id), cancelled);
  });

  it("cancel while the portal is verifying: the proof is discarded, its id never issued", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const world = new FakeWorld((signal) => [confirmed(orb(signal))], portalOrb);
    const realVerify = world.verify.bind(world);
    world.verify = async (p) => {
      await gate;
      return realVerify(p);
    };
    const { ap, store } = make(world);
    const { id } = await ap.start(own(store, OWNER), DIGEST);
    await waitFor(() => world.signals.length === 1 && ap.view(id)!.stage === "approve");
    await sleep(10);
    ap.cancel(id);
    release();
    await waitFor(() => world.verified.length === 1);
    await sleep(10);
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(store.useJti(jtiKey("idkit-approval", approvalJti(id, keyOf(OWNER))), 2), true, "never consumed");
  });

  it("cancel after an approval landed still answers ls_denied; unknown ids: false", async () => {
    const world = new FakeWorld((signal) => [confirmed(orb(signal))], portalOrb);
    const { ap, store } = make(world);
    const { id } = await ap.start(own(store, OWNER), DIGEST);
    assert.equal((await finish(ap, id)).ok, true);
    assert.equal(ap.cancel(id), true);
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(ap.cancel("nope"), false);
  });
});
