import assert from "node:assert/strict";
import { afterEach, before, describe, it } from "node:test";
import { AgentPass, StartFailure } from "../src/agentpass.js";
import type { DeviceGrantClient, DeviceStart, Discovery, PollResult } from "../src/oidc.js";
import { Store } from "../src/store.js";
import { CLIENT_ID, idToken, ISS, makeKeys, ORB, SECRET, sleep, tempDir, waitFor, type TestKeys } from "./helpers.js";

let keys: TestKeys;
before(async () => {
  keys = await makeKeys();
});

/** A scripted World IdP. Each poll takes the next answer; an empty script means "pending". */
class FakeIdp implements DeviceGrantClient {
  script: Array<PollResult | (() => Promise<PollResult>)> = [];
  pollTimes: number[] = [];
  startFails = false;
  constructor(private readonly start_: Partial<DeviceStart> = {}) {}
  async discover(): Promise<Discovery> {
    return { issuer: ISS, acrSupported: [ORB] };
  }
  async start(): Promise<DeviceStart> {
    if (this.startFails) throw new Error("invalid_client");
    return {
      device_code: "device-code-never-shown",
      user_code: "WDJB-MJHT",
      verification_uri: "https://auth.test.example/device",
      verification_uri_complete: "https://auth.test.example/device?user_code=WDJB-MJHT",
      expires_in: 1200,
      interval: 5,
      ...this.start_,
    };
  }
  async poll(): Promise<PollResult> {
    this.pollTimes.push(Date.now());
    const next = this.script.shift();
    if (!next) return { kind: "error", error: "authorization_pending", status: 400 };
    return typeof next === "function" ? next() : next;
  }
  keys() {
    return keys.getKey;
  }
}

const pending: PollResult = { kind: "error", error: "authorization_pending", status: 400 };
const tokens = async (over: Record<string, unknown> = {}): Promise<PollResult> => ({
  kind: "tokens",
  idToken: await idToken(keys.privateKey, over),
});

let live: AgentPass[] = [];
afterEach(() => {
  for (const a of live) a.stopAll();
  live = [];
});

function make(idp: FakeIdp, store = new Store(tempDir(), SECRET), over: Partial<ConstructorParameters<typeof AgentPass>[0]> = {}) {
  // One World "second" lasts 2 ms here, so interval 5 polls every 10 ms and 1200 s is 2.4 s.
  const ap = new AgentPass({ idp, store, secret: SECRET, clientId: CLIENT_ID, msPerSecond: 2, ...over });
  live.push(ap);
  return { ap, store };
}

async function finish(ap: AgentPass, id: string) {
  await waitFor(() => ap.view(id)?.stage === "done");
  return ap.view(id)!;
}

describe("Agent Pass approvals", () => {
  it("start returns World's complete link, the user code and the expiry, never the device code", async () => {
    const { ap } = make(new FakeIdp());
    const s = await ap.start("ANY-7QZ", "list SHIP 1:23.45 ghost");
    assert.deepEqual(Object.keys(s).sort(), ["code", "expires_s", "id", "qr"]);
    assert.equal(s.qr, "https://auth.test.example/device?user_code=WDJB-MJHT");
    assert.equal(s.code, "WDJB-MJHT");
    assert.equal(s.expires_s, 1200);
    assert.ok(!JSON.stringify(s).includes("device-code-never-shown"));
  });

  it("falls back to verification_uri when World sends no complete link", async () => {
    const { ap } = make(new FakeIdp({ verification_uri_complete: undefined }));
    assert.equal((await ap.start("ANY-7QZ", "a")).qr, "https://auth.test.example/device");
  });

  it("stays at stage scan until done (World sends no 'scanned' signal)", async () => {
    const idp = new FakeIdp();
    idp.script = [pending, pending, pending, () => tokens()];
    const { ap } = make(idp);
    const { id } = await ap.start("ANY-7QZ", "a");
    const seen = new Set<string>();
    await waitFor(() => {
      seen.add(ap.view(id)!.stage);
      return ap.view(id)!.stage === "done";
    });
    assert.deepEqual([...seen].sort(), ["done", "scan"]);
  });

  it("success: data is {jti}; the first approval binds the account to the book", async () => {
    const idp = new FakeIdp();
    idp.script = [() => tokens({ jti: "jti-first" })];
    const { ap, store } = make(idp);
    const { id } = await ap.start("ANY-7QZ", "list SHIP 1:23.45 ghost");
    const v = await finish(ap, id);
    assert.equal(v.ok, true);
    assert.equal(v.failure, null);
    assert.deepEqual(v.data, { jti: "jti-first" });
    assert.equal(store.checkBinding("ANY-7QZ", "anything-else"), "mismatch", "book is now bound");
  });

  it("the same account approves again for the same book: ok", async () => {
    const idp = new FakeIdp();
    const { ap } = make(idp);
    idp.script = [() => tokens({ sub: "owner" })];
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "a")).id)).ok, true);
    idp.script = [() => tokens({ sub: "owner" })];
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "b")).id)).ok, true);
  });

  it("another account approves for a bound book: ls_wrong", async () => {
    const idp = new FakeIdp();
    const { ap } = make(idp);
    idp.script = [() => tokens({ sub: "owner" })];
    await finish(ap, (await ap.start("ANY-7QZ", "a")).id);
    idp.script = [() => tokens({ sub: "intruder" })];
    const v = await finish(ap, (await ap.start("ANY-7QZ", "b")).id);
    assert.equal(v.ok, false);
    assert.equal(v.failure, "ls_wrong");
    assert.deepEqual(v.data, {});
  });

  it("a reused jti: ls_reused", async () => {
    const idp = new FakeIdp();
    const { ap } = make(idp);
    idp.script = [() => tokens({ jti: "same-jti" })];
    await finish(ap, (await ap.start("ANY-7QZ", "a")).id);
    idp.script = [() => tokens({ jti: "same-jti" })];
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "b")).id)).failure, "ls_reused");
  });

  it("a stale auth_time (authentication older than this attempt): ls_mismatch", async () => {
    const idp = new FakeIdp();
    idp.script = [() => tokens({ auth_time: Math.floor(Date.now() / 1000) - 3600 })];
    const { ap } = make(idp);
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "a")).id)).failure, "ls_mismatch");
  });

  it("a token for another client: ls_mismatch, and nothing is bound", async () => {
    const idp = new FakeIdp();
    idp.script = [() => tokens({ aud: "other-client" })];
    const { ap, store } = make(idp);
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "a")).id)).failure, "ls_mismatch");
    assert.equal(store.checkBinding("ANY-7QZ", "x"), "bound", "still unbound");
  });

  const stops: Array<[string, PollResult, string]> = [
    ["the person taps Deny", { kind: "error", error: "access_denied", status: 400 }, "ls_denied"],
    ["the device code lapses", { kind: "error", error: "expired_token", status: 400 }, "ls_expired"],
    ["the code is dead", { kind: "error", error: "invalid_grant", status: 400 }, "ls_expired"],
    ["World answers 503", { kind: "error", status: 503 }, "ls_world_down"],
    ["World rate-limits (429)", { kind: "error", status: 429 }, "ls_world_down"],
    ["our client is refused", { kind: "error", error: "invalid_client", status: 401 }, "ls_world_down"],
  ];
  for (const [what, answer, failure] of stops) {
    it(`${what}: ${failure}`, async () => {
      const idp = new FakeIdp();
      idp.script = [pending, answer];
      const { ap } = make(idp);
      const v = await finish(ap, (await ap.start("ANY-7QZ", "a")).id);
      assert.equal(v.ok, false);
      assert.equal(v.failure, failure);
    });
  }

  it("slow_down adds 5 s to every later poll", async () => {
    const idp = new FakeIdp({ interval: 1 });
    idp.script = [pending, { kind: "error", error: "slow_down", status: 400 }, pending, () => tokens()];
    const { ap } = make(idp, undefined, { msPerSecond: 10 }); // interval 1 s = 10 ms; after slow_down 60 ms
    await finish(ap, (await ap.start("ANY-7QZ", "a")).id);
    const t = idp.pollTimes;
    assert.equal(t.length, 4);
    assert.ok(t[1] - t[0] < 45, "before slow_down: about one interval");
    assert.ok(t[2] - t[1] >= 55, "after slow_down: interval + 5 s");
    assert.ok(t[3] - t[2] >= 55, "and it stays slower");
  });

  it("connection failures back off, and a long outage ends as ls_world_down", async () => {
    const idp = new FakeIdp({ interval: 1 });
    idp.script = Array.from({ length: 50 }, () => ({ kind: "network" }) as PollResult);
    const { ap } = make(idp, undefined, { networkGraceMs: 40 });
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "a")).id)).failure, "ls_world_down");
  });

  it("a short connection blip is survived", async () => {
    const idp = new FakeIdp({ interval: 1 });
    idp.script = [{ kind: "network" }, () => tokens()];
    const { ap } = make(idp, undefined, { networkGraceMs: 5000 });
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "a")).id)).ok, true);
  });

  it("no answer before World's expiry: ls_expired", async () => {
    const { ap } = make(new FakeIdp({ expires_in: 20, interval: 1 }));
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "a")).id)).failure, "ls_expired");
  });

  it("a start World refuses throws StartFailure(ls_world_down)", async () => {
    const idp = new FakeIdp();
    idp.startFails = true;
    const { ap } = make(idp);
    await assert.rejects(ap.start("ANY-7QZ", "a"), (e: unknown) => e instanceof StartFailure && e.failure === "ls_world_down");
  });
});

describe("Circle on the console always wins", () => {
  const cancelled = { stage: "done", ok: false, failure: "ls_denied", data: {} };

  it("cancel answers done / ls_denied at once, and keeps answering it", async () => {
    const idp = new FakeIdp({ interval: 1 });
    const { ap } = make(idp);
    const { id } = await ap.start("ANY-7QZ", "list MDGP 1:42.83 ghost at 0.10 USDC");
    assert.equal(ap.cancel(id), true);
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(ap.cancel(id), true, "idempotent");
    await sleep(20);
    assert.deepEqual(ap.view(id), cancelled);
  });

  it("a phone approval after cancel binds nothing, burns its jti, and the answer stays ls_denied", async () => {
    const idp = new FakeIdp({ interval: 1 });
    idp.script = [pending, pending, () => tokens({ sub: "late-approver", jti: "late-jti" })];
    const lines: string[] = [];
    const { ap, store } = make(idp, undefined, { log: (l: string) => lines.push(l) });
    const { id } = await ap.start("ANY-7QZ", "list SHIP 1:23.45 ghost at 0.10 USDC");
    ap.cancel(id);
    await waitFor(() => lines.some((l) => l.includes("ignored")));
    assert.deepEqual(ap.view(id), cancelled);
    assert.equal(store.checkBinding("ANY-7QZ", "anyone"), "bound", "the book is still unbound");
    // The late token can never authorise anything: replaying it is refused.
    idp.script = [() => tokens({ sub: "late-approver", jti: "late-jti" })];
    assert.equal((await finish(ap, (await ap.start("ANY-7QZ", "b")).id)).failure, "ls_reused");
  });

  it("a wrong account after cancel changes nothing either", async () => {
    const idp = new FakeIdp({ interval: 1 });
    const lines: string[] = [];
    const { ap } = make(idp, undefined, { log: (l: string) => lines.push(l) });
    idp.script = [() => tokens({ sub: "owner" })];
    await finish(ap, (await ap.start("ANY-7QZ", "a")).id);
    idp.script = [pending, () => tokens({ sub: "intruder" })];
    const { id } = await ap.start("ANY-7QZ", "b");
    ap.cancel(id);
    await waitFor(() => lines.some((l) => l.includes("after Circle: ls_wrong")));
    assert.deepEqual(ap.view(id), cancelled);
  });

  it("a deny after cancel changes nothing", async () => {
    const idp = new FakeIdp({ interval: 1 });
    const lines: string[] = [];
    const { ap } = make(idp, undefined, { log: (l: string) => lines.push(l) });
    idp.script = [pending, { kind: "error", error: "access_denied", status: 400 }];
    const { id } = await ap.start("ANY-7QZ", "a");
    ap.cancel(id);
    await waitFor(() => lines.some((l) => l.includes("after Circle: ls_denied")));
    assert.deepEqual(ap.view(id), cancelled);
  });

  it("cancel after an approval already landed still answers ls_denied (the console acts on nothing)", async () => {
    const idp = new FakeIdp({ interval: 1 });
    idp.script = [() => tokens({ jti: "done-jti" })];
    const { ap } = make(idp);
    const { id } = await ap.start("ANY-7QZ", "a");
    await finish(ap, id);
    assert.equal(ap.view(id)!.ok, true);
    assert.equal(ap.cancel(id), true);
    assert.deepEqual(ap.view(id), cancelled);
  });

  it("after cancel the bridge stops listening after a while", async () => {
    const idp = new FakeIdp({ interval: 1 });
    const { ap } = make(idp, undefined, { cancelListenMs: 20 });
    const { id } = await ap.start("ANY-7QZ", "a");
    ap.cancel(id);
    await sleep(40);
    const polls = idp.pollTimes.length;
    await sleep(30);
    assert.equal(idp.pollTimes.length, polls, "no polling after it stopped");
    assert.deepEqual(ap.view(id), cancelled);
  });

  it("unknown ids: false", () => {
    const { ap } = make(new FakeIdp());
    assert.equal(ap.cancel("nope"), false);
  });
});
