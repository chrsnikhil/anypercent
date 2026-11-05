import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { afterEach, describe, it } from "node:test";
import { StartFailure } from "../src/approvals.js";
import { jtiKey, nullifierKey } from "../src/hmac.js";
import { approvalJti, IdkitApprovals } from "../src/idkit-approvals.js";
import { Store } from "../src/store.js";
import {
  ACTION,
  awaiting,
  confirmed,
  failed,
  FakeWorld,
  proof,
  SESSION_A,
  SESSION_B,
  sessionProof,
  waiting,
} from "./fake-world.js";
import { SECRET, sleep, tempDir, waitFor } from "./helpers.js";

const DIGEST = "List Marine Drive GP 1:42.83 ghost for 0.10 USDC";

/** A book signed up with this World ID session (or none). */
function book(store: Store, nullifierLabel = "a", session: string | null = SESSION_A): string {
  return store.claimBook(nullifierKey(SECRET, ACTION, `nil_${nullifierLabel}`), "Orb", "runner", 1, session ?? undefined).record.book;
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

/** The book owner's World App proving its session for this approval's signal. */
const owner = (signal: string) => [confirmed(sessionProof(signal))];

describe("listing approvals on IDKit sessions", () => {
  it("is the idkit provider", () => {
    assert.equal(make(new FakeWorld(() => [waiting])).ap.kind, "idkit");
  });

  it("asks World App to prove the BOOK's session, showing the listing as the action description", async () => {
    const world = new FakeWorld(() => [waiting]);
    const { ap, store } = make(world);
    const s = await ap.start(book(store), DIGEST);
    assert.deepEqual(Object.keys(s).sort(), ["code", "expires_s", "id", "qr"]);
    assert.equal(s.qr, "https://staging.world.org/verify?t=fake-proveSession");
    assert.match(s.code, /^[A-Z2-9]{3}-[A-Z2-9]{3}$/);
    assert.equal(s.expires_s, 300);
    assert.equal(world.created[0].kind, "proveSession");
    assert.equal(world.created[0].sessionId, SESSION_A);
    assert.equal(world.created[0].description, DIGEST);
    assert.deepEqual(ap.view(s.id), { stage: "scan", ok: null, failure: null, data: {} });
    assert.ok(!JSON.stringify(s).includes(SESSION_A), "the session id is never returned");
  });

  it("the signal is anyl1|<book>|<sha256(digest)[:16]>|<approval id>, never 0x", async () => {
    const world = new FakeWorld(() => [waiting]);
    const { ap, store } = make(world);
    const b = book(store);
    const s = await ap.start(b, DIGEST);
    const digest16 = createHash("sha256").update(DIGEST).digest("hex").slice(0, 16);
    assert.equal(world.signals[0], `anyl1|${b}|${digest16}|${s.id}`);
  });

  it("walks scan -> approve -> done; the owner's session proof gives a one-time {jti}", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const world = new FakeWorld((signal) => [waiting, waiting, awaiting, awaiting, confirmed(sessionProof(signal))]);
    const realVerify = world.verify.bind(world);
    world.verify = async (p) => {
      await gate;
      return realVerify(p);
    };
    const { ap, store, lines } = make(world);
    const { id } = await ap.start(book(store), DIGEST);
    const seen: string[] = [];
    const record = () => {
      const st = ap.view(id)!.stage;
      if (seen[seen.length - 1] !== st) seen.push(st);
    };
    await waitFor(() => (record(), seen.includes("approve")));
    release();
    await waitFor(() => (record(), ap.view(id)!.stage === "done"));
    assert.deepEqual(seen, ["scan", "approve", "done"]);
    const v = ap.view(id)!;
    assert.equal(v.ok, true);
    assert.equal(v.failure, null);
    assert.deepEqual(Object.keys(v.data), ["jti"]);
    assert.equal(v.data.jti, approvalJti(id, world.created[0].nonce));
    const all = lines.join("\n");
    assert.match(all, /approved/);
    assert.ok(!all.includes(String(v.data.jti)), "no jti in the log");
    assert.ok(!all.includes(SESSION_A), "no session id in the log");
  });

  it("forwards the session proof to the portal unchanged", async () => {
    let sent: unknown;
    const world = new FakeWorld((signal) => [confirmed((sent = sessionProof(signal)))]);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).ok, true);
    assert.equal(world.verified[0], sent);
  });

  it("each approval is a fresh one-time id", async () => {
    const world = new FakeWorld(owner);
    const { ap, store } = make(world);
    const b = book(store);
    const a = await finish(ap, (await ap.start(b, DIGEST)).id);
    const c = await finish(ap, (await ap.start(b, DIGEST)).id);
    assert.equal(a.ok && c.ok, true);
    assert.notEqual(a.data.jti, c.data.jti);
  });

  it("an approval id already used: ls_reused", async () => {
    const world = new FakeWorld((signal) => [waiting, waiting, waiting, confirmed(sessionProof(signal))]);
    const { ap, store } = make(world, undefined, { pollMs: 10 });
    const { id } = await ap.start(book(store), DIGEST);
    assert.equal(store.useJti(jtiKey("idkit-approval", approvalJti(id, world.created[0].nonce)), 1), true);
    assert.equal((await finish(ap, id)).failure, "ls_reused");
  });

  it("a book with no World session: ls_wrong at once, nothing sent to World, logged as 'sign up again'", async () => {
    const world = new FakeWorld(() => [waiting]);
    const { ap, store, lines } = make(world);
    const s = await ap.start(book(store, "a", null), DIGEST);
    assert.equal(s.qr, "");
    assert.deepEqual(ap.view(s.id), { stage: "done", ok: false, failure: "ls_wrong", data: {} });
    assert.equal(world.created.length, 0);
    assert.match(lines.join("\n"), /this book has no World session: sign up again/);
  });

  it("a book this bridge never issued: ls_wrong", async () => {
    const { ap } = make(new FakeWorld(() => [waiting]));
    assert.equal((await finish(ap, (await ap.start("ANY-ZZZ", DIGEST)).id)).failure, "ls_wrong");
  });

  it("a proof of ANOTHER session (another book's owner): ls_mismatch, portal never asked", async () => {
    const world = new FakeWorld((signal) => [confirmed(sessionProof(signal, SESSION_B))]);
    const { ap, store, lines } = make(world);
    assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_mismatch");
    assert.equal(world.verified.length, 0);
    assert.match(lines.join("\n"), /another World session/);
    assert.ok(!lines.join("\n").includes(SESSION_B));
  });

  it("the portal naming another session than the proof's: ls_mismatch", async () => {
    const world = new FakeWorld(owner, () => ({
      status: 200,
      body: { success: true, session_id: SESSION_B, results: [{ identifier: "proof_of_human", success: true }] },
    }));
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_mismatch");
  });

  it("a sign-up (uniqueness) proof in place of a session proof: ls_mismatch", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))]);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_mismatch");
    assert.equal(world.verified.length, 0);
  });

  const appFailures: Array<[string, string]> = [
    ["user_rejected", "ls_denied"],
    ["cancelled", "ls_denied"],
    ["timeout", "ls_expired"],
    ["credential_unavailable", "ls_wrong"],
    ["invalid_rp_signature", "ls_world_down"],
    ["connection_failed", "ls_world_down"],
    ["nullifier_replayed", "ls_reused"],
  ];
  for (const [code, failure] of appFailures) {
    it(`World App answers ${code}: ${failure}, and the log names World App's code`, async () => {
      const { ap, store, lines } = make(new FakeWorld(() => [waiting, awaiting, failed(code)]));
      const v = await finish(ap, (await ap.start(book(store), DIGEST)).id);
      assert.deepEqual(v, { stage: "done", ok: false, failure, data: {} });
      assert.match(lines.join("\n"), new RegExp(`World App: ${code}`));
    });
  }

  it("a proof bound to another request (signal): ls_mismatch, portal never asked", async () => {
    const world = new FakeWorld(() => [confirmed(sessionProof("anyl1|ANY-XXX|0000|other"))]);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_mismatch");
    assert.equal(world.verified.length, 0);
  });

  it("another environment or a legacy 3.0 proof: ls_mismatch", async () => {
    for (const over of [{ environment: "production" }, { protocol_version: "3.0" }]) {
      const world = new FakeWorld((signal) => [confirmed(sessionProof(signal, SESSION_A, over))]);
      const { ap, store } = make(world);
      assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_mismatch");
      assert.equal(world.verified.length, 0);
    }
  });

  it("the portal refusing the proof: ls_mismatch; refusing a replay: ls_reused", async () => {
    const refused = new FakeWorld(owner, () => ({
      status: 400,
      body: { success: false, code: "all_verifications_failed", results: [{ code: "verification_error" }] },
    }));
    const a = make(refused);
    assert.equal((await finish(a.ap, (await a.ap.start(book(a.store), DIGEST)).id)).failure, "ls_mismatch");
    const replay = new FakeWorld(owner, () => ({ status: 400, body: { success: false, code: "nullifier_replayed" } }));
    const b = make(replay);
    assert.equal((await finish(b.ap, (await b.ap.start(book(b.store), DIGEST)).id)).failure, "ls_reused");
  });

  it("the portal down, 5xx or unreachable: ls_world_down", async () => {
    for (const portal of [() => new Error("ECONNRESET"), () => ({ status: 502, body: undefined }), () => ({ status: 404, body: {} })]) {
      const world = new FakeWorld(owner, portal);
      const { ap, store } = make(world);
      assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_world_down");
    }
  });

  it("a credential we do not accept: ls_wrong", async () => {
    const world = new FakeWorld((signal) => [confirmed(sessionProof(signal, SESSION_A, {}, { identifier: "passport", issuer_schema_id: 9303 }))]);
    const { ap, store } = make(world);
    assert.equal((await finish(ap, (await ap.start(book(store), DIGEST)).id)).failure, "ls_wrong");
  });

  it("World's bridge unreachable for too long: ls_world_down; a blip is survived", async () => {
    const out = make(new FakeWorld(() => [new Error("fetch failed")]), undefined, { networkGraceMs: 30 });
    assert.equal((await finish(out.ap, (await out.ap.start(book(out.store), DIGEST)).id)).failure, "ls_world_down");
    const blip = make(new FakeWorld((signal) => [new Error("fetch failed"), confirmed(sessionProof(signal))]), undefined, {
      networkGraceMs: 5000,
    });
    assert.equal((await finish(blip.ap, (await blip.ap.start(book(blip.store), DIGEST)).id)).ok, true);
  });

  it("no answer within the lifetime: ls_expired", async () => {
    let t = Date.now();
    const { ap, store } = make(new FakeWorld(() => [waiting]), undefined, { now: () => t, ttlS: 1 });
    const { id } = await ap.start(book(store), DIGEST);
    t += 7000;
    assert.equal((await finish(ap, id)).failure, "ls_expired");
  });

  it("a request World's bridge will not create: StartFailure(ls_world_down)", async () => {
    const world = new FakeWorld(() => [waiting]);
    world.createFails = true;
    const { ap, store } = make(world);
    await assert.rejects(
      ap.start(book(store), DIGEST),
      (e: unknown) => e instanceof StartFailure && e.failure === "ls_world_down" && e.status === 503,
    );
  });
});

describe("IDKit approvals: Circle on the console always wins", () => {
  const cancelled = { stage: "done", ok: false, failure: "ls_denied", data: {} };

  it("cancel answers done / ls_denied at once, idempotently, and stops polling", async () => {
    const world = new FakeWorld((signal) => [awaiting, awaiting, awaiting, awaiting, confirmed(sessionProof(signal))]);
    const { ap, store } = make(world, undefined, { pollMs: 5 });
    const { id } = await ap.start(book(store), DIGEST);
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
    const world = new FakeWorld(owner);
    const realVerify = world.verify.bind(world);
    world.verify = async (p) => {
      await gate;
      return realVerify(p);
    };
    const { ap, store } = make(world);
    const { id } = await ap.start(book(store), DIGEST);
    await waitFor(() => world.signals.length === 1 && ap.view(id)!.stage === "approve");
    await sleep(10);
    ap.cancel(id);
    release();
    await waitFor(() => world.verified.length === 1);
    await sleep(10);
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(store.useJti(jtiKey("idkit-approval", approvalJti(id, world.created[0].nonce)), 2), true, "never consumed");
  });

  it("cancel after an approval landed still answers ls_denied; unknown ids: false", async () => {
    const world = new FakeWorld(owner);
    const { ap, store } = make(world);
    const { id } = await ap.start(book(store), DIGEST);
    assert.equal((await finish(ap, id)).ok, true);
    assert.equal(ap.cancel(id), true);
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(ap.cancel("nope"), false);
  });
});
