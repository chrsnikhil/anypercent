import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { Nullifier } from "@worldcoin/idkit-core/nullifier";
import { nullifierKey } from "../src/hmac.js";
import { IdkitSessions, IdkitStartFailure } from "../src/idkit.js";
import { Store } from "../src/store.js";
import { ACTION, awaiting, confirmed, failed, FakeWorld, portalOk, proof, SESSION_A, SESSION_B, sessionProof, waiting } from "./fake-world.js";
import { SECRET, sleep, tempDir, waitFor } from "./helpers.js";

let live: IdkitSessions[] = [];
afterEach(() => {
  for (const s of live) s.stopAll();
  live = [];
});

function make(world: FakeWorld, store = new Store(tempDir(), SECRET), over: Record<string, unknown> = {}) {
  const s = new IdkitSessions({
    deps: world,
    store,
    secret: SECRET,
    action: ACTION,
    environment: "staging",
    pollMs: 2,
    ...over,
  });
  live.push(s);
  return { idkit: s, store };
}

async function finish(idkit: IdkitSessions, id: string) {
  await waitFor(() => idkit.view(id)?.stage === "done");
  return idkit.view(id)!;
}

describe("IDKit record book", () => {
  it("start returns the World App link, an XXX-XXX display code and the TTL", async () => {
    const { idkit } = make(new FakeWorld(() => [waiting]));
    const s = await idkit.start("pi-booth");
    assert.deepEqual(Object.keys(s).sort(), ["code", "expires_s", "id", "qr"]);
    assert.equal(s.qr, "https://staging.world.org/verify?t=fake");
    assert.match(s.code, /^[A-Z2-9]{3}-[A-Z2-9]{3}$/);
    assert.equal(s.expires_s, 300);
    assert.deepEqual(idkit.view(s.id), { stage: "scan", ok: null, failure: null, data: {} });
  });

  it("the signal binds the proof to this sign-up and never starts with 0x", async () => {
    const world = new FakeWorld(() => [waiting]);
    const { idkit } = make(world);
    const a = await idkit.start("pi");
    const b = await idkit.start("pi");
    assert.ok(world.signals[0].startsWith("anyb1|"));
    assert.ok(world.signals[0].endsWith(`|${a.id}`));
    assert.ok(world.signals[1].endsWith(`|${b.id}`));
  });

  it("walks scan -> confirm -> verify -> done with {book, credential, runner_id}", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const world = new FakeWorld(
      (signal) => [waiting, waiting, awaiting, awaiting, confirmed(proof(signal, "0x0abc"))],
      () => portalOk(),
    );
    const realVerify = world.verify.bind(world);
    world.verify = async (p) => {
      await gate;
      return realVerify(p);
    };
    const { idkit } = make(world);
    const { id } = await idkit.start("pi");
    const seen: string[] = [];
    const record = () => {
      const st = idkit.view(id)!.stage;
      if (seen[seen.length - 1] !== st) seen.push(st);
    };
    await waitFor(() => (record(), idkit.view(id)!.stage === "verify"));
    assert.deepEqual(idkit.view(id), { stage: "verify", ok: null, failure: null, data: {} });
    release();
    await waitFor(() => (record(), idkit.view(id)!.stage === "done"));
    assert.deepEqual(seen, ["scan", "confirm", "verify", "done"]);
    const v = idkit.view(id)!;
    assert.equal(v.ok, true);
    assert.equal(v.failure, null);
    assert.deepEqual(Object.keys(v.data).sort(), ["book", "credential", "runner_id"]);
    assert.match(String(v.data.book), /^ANY-[A-Z2-9]{3}$/);
    assert.equal(v.data.credential, "Selfie Check");
    assert.match(String(v.data.runner_id), /^[0-9a-f]{16}$/);
    assert.ok(!JSON.stringify(v).toLowerCase().includes("0abc"), "no raw nullifier in the answer");
  });

  it("forwards the IDKit result to the portal unchanged", async () => {
    let sent: unknown;
    const world = new FakeWorld((signal) => [confirmed((sent = proof(signal, "0x0abc")))]);
    const { idkit } = make(world);
    await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(world.verified[0], sent);
  });

  it("an Orb proof reports credential Orb", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(proof(signal, "0x0abd", {}, { identifier: "proof_of_human", issuer_schema_id: 1, sybil_score: undefined }))],
      () => portalOk("proof_of_human"),
    );
    const { idkit } = make(world);
    assert.equal((await finish(idkit, (await idkit.start("pi")).id)).data.credential, "Orb");
  });

  it("the same human signing up again: id_dup carrying the existing book", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))]);
    const { idkit } = make(world);
    const first = await finish(idkit, (await idkit.start("pi")).id);
    const second = await finish(idkit, (await idkit.start("another-console")).id);
    assert.equal(second.ok, false);
    assert.equal(second.failure, "id_dup");
    assert.deepEqual(second.data, { book: first.data.book });
  });

  it("the nullifier's spelling does not matter (0x, case, leading zeros)", async () => {
    let n = 0;
    const spellings = ["0x0ABC", "0xabc", "0x000abc"];
    const world = new FakeWorld((signal) => [confirmed(proof(signal, spellings[n++]))]);
    const { idkit } = make(world);
    const a = await finish(idkit, (await idkit.start("pi")).id);
    const b = await finish(idkit, (await idkit.start("pi")).id);
    const c = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(a.ok, true);
    assert.deepEqual([b.failure, c.failure], ["id_dup", "id_dup"]);
    assert.equal(b.data.book, a.data.book);
  });

  it("different humans get different books", async () => {
    let n = 0;
    const world = new FakeWorld((signal) => [confirmed(proof(signal, n++ === 0 ? "0x01" : "0x02"))]);
    const { idkit } = make(world);
    const a = await finish(idkit, (await idkit.start("pi")).id);
    const b = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(b.ok, true);
    assert.notEqual(a.data.book, b.data.book);
  });

  it("the portal refusing a repeat: id_dup, naming the book this nullifier owns", async () => {
    let calls = 0;
    const world = new FakeWorld(
      (signal) => [confirmed(proof(signal, "0x0abc"))],
      () =>
        calls++ === 0
          ? portalOk()
          : { status: 400, body: { success: false, code: "all_verifications_failed", results: [{ code: "max_verifications_reached" }] } },
    );
    const { idkit } = make(world);
    const first = await finish(idkit, (await idkit.start("pi")).id);
    const again = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(again.failure, "id_dup");
    assert.deepEqual(again.data, { book: first.data.book });
  });

  it("World App refusing a repeat before any proof: id_dup without a book", async () => {
    const { idkit } = make(new FakeWorld(() => [awaiting, failed("max_verifications_reached")]));
    const v = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(v.failure, "id_dup");
    assert.deepEqual(v.data, {});
  });

  const appFailures: Array<[string, string]> = [
    ["user_rejected", "id_rejected"],
    ["credential_unavailable", "id_nocred"],
    ["timeout", "id_expired"],
    ["invalid_rp_signature", "id_offline"],
  ];
  for (const [code, failure] of appFailures) {
    it(`World App answers ${code}: ${failure}`, async () => {
      const { idkit } = make(new FakeWorld(() => [waiting, awaiting, failed(code)]));
      const v = await finish(idkit, (await idkit.start("pi")).id);
      assert.deepEqual(v, { stage: "done", ok: false, failure, data: {} });
    });
  }

  it("a proof bound to another signal (another sign-up's proof): id_rejected, portal never asked", async () => {
    const world = new FakeWorld(() => [confirmed(proof("anyb1|someone|else", "0x0abc"))]);
    const { idkit, store } = make(world);
    const v = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(v.failure, "id_rejected");
    assert.equal(world.verified.length, 0);
    assert.equal(store.bookFor("x"), undefined);
  });

  it("a proof from another environment: id_rejected", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", { environment: "production" }))]);
    const { idkit } = make(world);
    assert.equal((await finish(idkit, (await idkit.start("pi")).id)).failure, "id_rejected");
    assert.equal(world.verified.length, 0);
  });

  it("a proof for another action or a legacy 3.0 proof: id_rejected", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", { action: "other" }))]);
    const { idkit } = make(world);
    assert.equal((await finish(idkit, (await idkit.start("pi")).id)).failure, "id_rejected");
    const legacy = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", { protocol_version: "3.0" }))]);
    const m = make(legacy);
    assert.equal((await finish(m.idkit, (await m.idkit.start("pi")).id)).failure, "id_rejected");
  });

  it("the portal says the proof is invalid: id_rejected, no book", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(proof(signal, "0x0abc"))],
      () => ({ status: 400, body: { success: false, code: "all_verifications_failed", results: [{ code: "verification_error" }] } }),
    );
    const { idkit } = make(world);
    assert.equal((await finish(idkit, (await idkit.start("pi")).id)).failure, "id_rejected");
  });

  it("the portal answers for another environment: id_rejected", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(proof(signal, "0x0abc"))],
      () => ({ status: 200, body: { success: true, environment: "production", results: [] } }),
    );
    const { idkit } = make(world);
    assert.equal((await finish(idkit, (await idkit.start("pi")).id)).failure, "id_rejected");
  });

  it("a credential we do not accept: id_nocred", async () => {
    const passport = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", {}, { issuer_schema_id: 9303, identifier: "passport" }))]);
    const b = make(passport);
    assert.equal((await finish(b.idkit, (await b.idkit.start("pi")).id)).failure, "id_nocred");
  });

  it("expires_at_min is the request's lower bound, not the credential's expiry: a past one still makes a book", async () => {
    // A real World App proof carries expires_at_min = about the request's time, so it is seconds in the past by the
    // time the portal has verified it. The portal checks validity; reading it as a lapse refused every real Orb.
    const real = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", {}, {
      identifier: "proof_of_human", issuer_schema_id: 1, expires_at_min: Math.floor(Date.now() / 1000) - 20 }))]);
    const a = make(real);
    const v = await finish(a.idkit, (await a.idkit.start("pi")).id);
    assert.equal(v.failure, null);
    assert.equal(v.data.credential, "Orb");
  });

  it("the portal unreachable or 5xx: id_offline", async () => {
    const down = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))], () => new Error("ECONNRESET"));
    const a = make(down);
    assert.equal((await finish(a.idkit, (await a.idkit.start("pi")).id)).failure, "id_offline");
    const five = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))], () => ({ status: 502, body: undefined }));
    const b = make(five);
    assert.equal((await finish(b.idkit, (await b.idkit.start("pi")).id)).failure, "id_offline");
  });

  it("the bridge unreachable for too long: id_offline; a blip is survived", async () => {
    const out = new FakeWorld(() => [new Error("fetch failed")]);
    const a = make(out, undefined, { networkGraceMs: 30 });
    assert.equal((await finish(a.idkit, (await a.idkit.start("pi")).id)).failure, "id_offline");
    const blip = new FakeWorld((signal) => [new Error("fetch failed"), confirmed(proof(signal, "0x0abc"))]);
    const b = make(blip, undefined, { networkGraceMs: 5000 });
    assert.equal((await finish(b.idkit, (await b.idkit.start("pi")).id)).ok, true);
  });

  it("no answer within the TTL: id_expired", async () => {
    let t = Date.now();
    const { idkit } = make(new FakeWorld(() => [waiting]), undefined, { now: () => t, ttlS: 1 });
    const { id } = await idkit.start("pi");
    t += 7000;
    assert.equal((await finish(idkit, id)).failure, "id_expired");
  });

  const cancelled = { stage: "done", ok: false, failure: "id_rejected", data: {} };

  it("cancel stops the sign-up: a later Confirm is never verified and makes no book", async () => {
    const world = new FakeWorld((signal) => [awaiting, awaiting, awaiting, awaiting, awaiting, confirmed(proof(signal, "0x0abc"))]);
    const { idkit } = make(world, undefined, { pollMs: 5 });
    const { id } = await idkit.start("pi");
    await waitFor(() => idkit.view(id)!.stage === "confirm");
    assert.equal(idkit.cancel(id), true);
    assert.deepEqual(idkit.view(id), cancelled);
    assert.equal(idkit.cancel(id), true, "idempotent");
    await sleep(60);
    assert.equal(world.verified.length, 0);
    assert.deepEqual(idkit.view(id), cancelled);
  });

  it("cancel while the portal is verifying: the proof is discarded, no book is made", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))]);
    const realVerify = world.verify.bind(world);
    world.verify = async (p) => {
      await gate;
      return realVerify(p);
    };
    const { idkit } = make(world);
    const { id } = await idkit.start("pi");
    await waitFor(() => idkit.view(id)!.stage === "verify");
    idkit.cancel(id);
    release();
    await waitFor(() => world.verified.length === 1);
    await sleep(10);
    assert.deepEqual(idkit.view(id), cancelled);
    // No book was made: the same human signing up again gets a NEW book, not id_dup.
    world.verify = realVerify;
    const again = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(again.ok, true);
  });

  it("cancel after a book was made still answers id_rejected; unknown ids: false", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))]);
    const { idkit } = make(world);
    const { id } = await idkit.start("pi");
    await finish(idkit, id);
    assert.equal(idkit.cancel(id), true);
    assert.deepEqual(idkit.view(id), cancelled);
    assert.equal(idkit.cancel("nope"), false);
  });

  it("a request World's bridge will not create: IdkitStartFailure(id_offline)", async () => {
    const world = new FakeWorld(() => [waiting]);
    world.createFails = true;
    const { idkit } = make(world);
    await assert.rejects(idkit.start("pi"), (e: unknown) => e instanceof IdkitStartFailure && e.failure === "id_offline");
  });
});

describe("the record book's World ID session", () => {
  const noSession = { session_id: undefined };
  const isSession = (signal: string) => signal.startsWith("anys1|");
  /** The stored record of the human behind nullifier 0x0abc. */
  const humanRecord = (store: Store) => store.bookFor(nullifierKey(SECRET, ACTION, Nullifier.fromHex("0x0abc").toCanonicalString()));

  function logged(over: Record<string, unknown> = {}) {
    const lines: string[] = [];
    return { lines, over: { log: (l: string) => lines.push(l), ...over } };
  }

  it("the sign-up is ONE uniqueness request that also creates the session; the session is stored, never returned or logged", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))]);
    const { lines, over } = logged();
    const { idkit, store } = make(world, undefined, over);
    const v = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(v.ok, true);
    assert.deepEqual(world.created.map((c) => c.kind), ["request"]);
    assert.equal(store.recordForBook(String(v.data.book))?.session_id, SESSION_A);
    assert.ok(!JSON.stringify(v).includes("session_"), "never in the answer");
    assert.ok(!lines.join("\n").includes(SESSION_A), "never in the log");
  });

  it("combined mode, a result with no session: the book is made, and the log says approvals will fail", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", noSession))]);
    const { lines, over } = logged();
    const { idkit, store } = make(world, undefined, over);
    const v = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(v.ok, true);
    assert.equal(store.recordForBook(String(v.data.book))?.session_id, undefined);
    assert.match(lines.join("\n"), /no World session in the sign-up proof/);
    assert.match(lines.join("\n"), /WORLD_SIGNUP_SESSION=separate/);
  });

  it("the portal naming another session than the proof's: id_rejected, no book", async () => {
    const world = new FakeWorld(
      (signal) => [confirmed(proof(signal, "0x0abc"))],
      () => ({ status: 200, body: { success: true, action: ACTION, session_id: SESSION_B, results: [] } }),
    );
    const { idkit } = make(world);
    assert.equal((await finish(idkit, (await idkit.start("pi")).id)).failure, "id_rejected");
  });

  it("a malformed session id in the sign-up proof is not stored", async () => {
    const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc", { session_id: "not-a-session" }))]);
    const { idkit, store } = make(world);
    const v = await finish(idkit, (await idkit.start("pi")).id);
    assert.equal(v.ok, true);
    assert.equal(store.recordForBook(String(v.data.book))?.session_id, undefined);
  });

  describe("fallback: WORLD_SIGNUP_SESSION=separate", () => {
    const separate = { signupSession: "separate" };

    it("a result with a session needs no second scan", async () => {
      const world = new FakeWorld((signal) => [confirmed(proof(signal, "0x0abc"))]);
      const { idkit } = make(world, undefined, separate);
      assert.equal((await finish(idkit, (await idkit.start("pi")).id)).ok, true);
      assert.deepEqual(world.created.map((c) => c.kind), ["request"]);
    });

    it("no session: a createSession scan follows; verify carries its QR; done once the session is stored", async () => {
      let release!: () => void;
      const gate = new Promise<void>((r) => (release = r));
      const world = new FakeWorld((signal) =>
        isSession(signal) ? [waiting, awaiting, confirmed(sessionProof(signal, SESSION_B))] : [confirmed(proof(signal, "0x0abc", noSession))],
      );
      const realCreate = world.createSession.bind(world);
      world.createSession = async (signal) => {
        await gate;
        return realCreate(signal);
      };
      const { lines, over } = logged(separate);
      const { idkit, store } = make(world, undefined, over);
      const { id } = await idkit.start("pi");
      await waitFor(() => world.verified.length === 1);
      await sleep(5);
      assert.equal(idkit.view(id)!.stage, "verify");
      release();
      await waitFor(() => typeof idkit.view(id)!.data.session_qr === "string" || idkit.view(id)!.stage === "done");
      const mid = idkit.view(id)!;
      assert.equal(mid.stage, "verify");
      assert.equal(mid.data.session_qr, "https://staging.world.org/verify?t=fake-createSession");
      assert.match(String(mid.data.session_code), /^[A-Z2-9]{3}-[A-Z2-9]{3}$/);
      assert.ok(world.signals[1].startsWith(`anys1|${id}`));
      const v = await finish(idkit, id);
      assert.equal(v.ok, true);
      assert.deepEqual(Object.keys(v.data).sort(), ["book", "credential", "runner_id"]);
      assert.equal(store.recordForBook(String(v.data.book))?.session_id, SESSION_B);
      assert.ok(!lines.join("\n").includes(SESSION_B));
      assert.match(lines.join("\n"), /World session stored/);
    });

    it("the session scan refused on the phone: id_rejected; the book stays, without a session", async () => {
      const world = new FakeWorld((signal) =>
        isSession(signal) ? [awaiting, failed("user_rejected")] : [confirmed(proof(signal, "0x0abc", noSession))],
      );
      const { lines, over } = logged(separate);
      const { idkit, store } = make(world, undefined, over);
      const v = await finish(idkit, (await idkit.start("pi")).id);
      assert.equal(v.failure, "id_rejected");
      assert.match(lines.join("\n"), /World App: user_rejected/);
      assert.match(lines.join("\n"), /the book has no session yet/);
      assert.equal(world.verified.length, 1);
      assert.ok(humanRecord(store), "the book was made");
      assert.equal(humanRecord(store)?.session_id, undefined, "without a session");
    });

    it("a session proof for another request: id_rejected, no session stored", async () => {
      const world = new FakeWorld((signal) =>
        isSession(signal) ? [confirmed(sessionProof("anys1|someone-else"))] : [confirmed(proof(signal, "0x0abc", noSession))],
      );
      const { idkit, store } = make(world, undefined, separate);
      const { id } = await idkit.start("pi");
      const v = await finish(idkit, id);
      assert.equal(v.failure, "id_rejected");
      assert.equal(world.verified.length, 1, "the session proof never reached the portal");
      assert.equal(humanRecord(store)?.session_id, undefined);
    });

    it("Circle during the session scan: id_rejected, nothing stored", async () => {
      const world = new FakeWorld((signal) =>
        isSession(signal) ? [awaiting, awaiting, awaiting, awaiting, confirmed(sessionProof(signal, SESSION_B))] : [confirmed(proof(signal, "0x0abc", noSession))],
      );
      const { idkit, store } = make(world, undefined, { ...separate, pollMs: 5 });
      const { id } = await idkit.start("pi");
      await waitFor(() => typeof idkit.view(id)!.data.session_qr === "string");
      idkit.cancel(id);
      await sleep(60);
      assert.deepEqual(idkit.view(id), { stage: "done", ok: false, failure: "id_rejected", data: {} });
      assert.equal(world.verified.length, 1);
      assert.equal(humanRecord(store)?.session_id, undefined);
    });

    it("a repeat sign-up the portal refuses names the book, and gives a book without a session its session", async () => {
      let calls = 0;
      const world = new FakeWorld(
        (signal) => (isSession(signal) ? [confirmed(sessionProof(signal, SESSION_B))] : [confirmed(proof(signal, "0x0abc", noSession))]),
        (payload) => {
          const p = payload as { action?: unknown };
          if (p.action === undefined) return { status: 200, body: { success: true, session_id: SESSION_B, results: [] } };
          return calls++ === 0
            ? portalOk()
            : { status: 400, body: { success: false, code: "all_verifications_failed", results: [{ code: "nullifier_replayed" }] } };
        },
      );
      const { idkit, store } = make(world, undefined, { signupSession: "combined" });
      const first = await finish(idkit, (await idkit.start("pi")).id);
      assert.equal(humanRecord(store)?.session_id, undefined);
      // The owner switches the fallback on and signs up again.
      const again = make(world, store, separate);
      const v = await finish(again.idkit, (await again.idkit.start("pi")).id);
      assert.equal(v.failure, "id_dup");
      assert.deepEqual(v.data, { book: first.data.book });
      assert.equal(humanRecord(store)?.session_id, SESSION_B);
    });
  });
});
