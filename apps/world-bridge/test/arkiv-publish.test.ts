/**
 * POST /arkiv/publish's pipeline against a fake Arkiv, a fake checker and a fake clock: the checks,
 * the run and listing issued for the console to sign (the bridge writes no player row), the
 * console's report (`written`), the on-chain check of its entities and the checker's stamp.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { describe, it } from "node:test";
import type { ListingValues, RunValues } from "../src/arkiv/client.js";
import { decryptGhost } from "../src/arkiv/ghost.js";
import { actionText, fmtTime, parseBody, priceDec, priceText, PublishRefused, Publisher, type PublishView } from "../src/arkiv/publish.js";
import { STAMP_FLAGS } from "../src/arkiv/schema.js";
import { fromSpecJson } from "../src/arkiv/spec-json.js";
import { nullifierKey } from "../src/hmac.js";
import { Store } from "../src/store.js";
import { CHECKER, consoleFinish, FakeArkiv, FakeChecker, linkWallet, makeLog, WALLET_A, WALLET_B, type Issue } from "./fake-arkiv.js";
import { FakeSplits } from "./fake-splits.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const GHOST = "ab".repeat(32);
const TITLE = "MARINE DRIVE GP";
const T0 = 1_800_000_000_000;
const DAY = 86_400_000;
const CHAIN = 7794095;
const RPC = "https://rpc.rabdi.db-chain.testnet.arkiv.network";
const JTI = "3f9c0a1b2c3d4e5f";
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const sha256 = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

let seq = 0;

function setup(opts: { frames?: number; priceC?: number; link?: boolean; splits?: FakeSplits } = {}) {
  const store = new Store(tempDir(), SECRET);
  seq += 1;
  const rec = store.claimBook(nullifierKey(SECRET, "act", `nil-${seq}`), "Orb", "0123456789abcdef", 1, "session_x").record;
  const other = store.claimBook(nullifierKey(SECRET, "act", `nil-other-${seq}`), "Selfie Check", "fedcba9876543210", 1, "session_y").record;
  const arkiv = new FakeArkiv();
  const checker = new FakeChecker(opts.frames ?? 6170);
  const clock = { ms: T0 };
  const lines: string[] = [];
  const pub = new Publisher({
    arkiv,
    checker,
    store,
    season: 1,
    runExpiry: new Date(T0 + 60 * DAY),
    priceC: opts.priceC ?? 10,
    ghostSecret: GHOST,
    chainId: CHAIN,
    rpc: RPC,
    ...(opts.splits ? { splits: opts.splits } : {}),
    now: () => clock.ms,
    log: (l) => lines.push(l),
    writeTimeoutMs: 200,
    verifyGapMs: 1,
  });
  if (opts.link !== false) linkWallet(store, rec.book, WALLET_A);
  const action = actionText(TITLE, 6170, 10);
  /** A fresh approval for this book (as the approval providers record it). */
  const approve = (jti: string, book = rec.book, text = action) => store.recordApproval(jti, book, sha(text), Math.floor(clock.ms / 1000));
  const log = makeLog("MDGP");
  const body = (over: Record<string, unknown> = {}) => ({
    book: rec.book,
    jti: JTI,
    action,
    game: "MDGP",
    title: TITLE,
    frames: 6170,
    price_c: 10,
    log: Buffer.from(log).toString("base64"),
    ...over,
  });
  return { store, rec, other, arkiv, checker, clock, lines, pub, action, approve, log, body };
}

type S = ReturnType<typeof setup>;

async function finish(pub: Publisher, id: string): Promise<PublishView> {
  await waitFor(() => pub.view(id)?.stage === "done");
  return pub.view(id)!;
}

/** The whole listing: the bridge's checks, the console signing from WALLET_A, the stamp. */
async function publish(s: S, over: Record<string, unknown> = {}, wallet = WALLET_A): Promise<PublishView> {
  const { id, expires_s } = s.pub.start(s.body(over));
  assert.equal(expires_s, 120);
  return consoleFinish(s.pub, s.arkiv, id, wallet);
}

/** Up to the sign stage (or done when the job ends before it). */
async function issued(s: S, over: Record<string, unknown> = {}): Promise<{ id: string; view: PublishView }> {
  const { id } = s.pub.start(s.body(over));
  await waitFor(() => s.pub.view(id)?.stage === "sign" || s.pub.view(id)?.stage === "done");
  return { id, view: s.pub.view(id)! };
}

const issueOf = (v: PublishView) => JSON.parse(JSON.stringify(v.data.issue)) as Issue;

/** The run values the checker used to write, and the console now writes (log_enc aside). */
function expectedRun(s: S) {
  return {
    game: "MDGP",
    title: TITLE,
    season: 1,
    rules: 4,
    frames: 6170,
    log_h: sha256(s.log),
    runner: "0123456789abcdef",
    book: s.rec.book,
    human: true,
    credential: "Orb",
    tool: "arcade_replay sha256:a992006e6280",
  };
}

describe("format helpers (coach.fmt_time, the launcher's price)", () => {
  it("fmtTime: 6170 -> 1:42.83, 6290 -> 1:44.83, 60 -> 0:01.00", () => {
    assert.equal(fmtTime(6170), "1:42.83");
    assert.equal(fmtTime(6290), "1:44.83");
    assert.equal(fmtTime(60), "0:01.00");
    assert.equal(fmtTime(3600 * 60 + 1), "60:00.02");
  });
  it("price: 10 cents -> '0.10' in text, '0.1' as a dec", () => {
    assert.equal(priceText(10), "0.10");
    assert.equal(priceText(150), "1.50");
    assert.equal(priceDec(10), "0.1");
    assert.equal(priceDec(150), "1.5");
    assert.equal(priceDec(200), "2");
  });
  it("the approved text", () => {
    assert.equal(actionText(TITLE, 6170, 10), "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC on the public board");
  });
});

describe("publish: issue, the console signs, the checker stamps", () => {
  it("issues the run and its listing at the sign stage, exactly what the checker used to write; the bridge writes nothing", async () => {
    const s = setup();
    s.approve(JTI);
    const { view: v } = await issued(s);
    assert.equal(v.stage, "sign", JSON.stringify(v));
    assert.deepEqual([v.ok, v.failure], [null, null]);
    const issue = issueOf(v);
    assert.deepEqual(Object.keys(issue).sort(), ["chain_id", "listing", "replaces", "rpc", "run", "run_key"]);
    assert.deepEqual([issue.chain_id, issue.rpc, issue.run_key, issue.replaces], [CHAIN, RPC, null, null]);

    const run = fromSpecJson<RunValues>(issue.run);
    const logH = sha256(s.log);
    assert.deepEqual({ ...run.values, log_enc: undefined }, { ...expectedRun(s), log_enc: undefined });
    assert.equal(run.values.log, undefined, "a listed run never carries the plain log");
    assert.equal(run.values.label, undefined, "a World-tier run has no label");
    assert.deepEqual(run.flags, { readonly: true, permissionlessExtension: true });
    assert.deepEqual(run.expiry, { kind: "atDate", date: new Date(T0 + 60 * DAY), atLeastDays: 1 });
    assert.ok(run.values.log_enc instanceof Uint8Array);
    assert.deepEqual(decryptGhost(GHOST, logH, run.values.log_enc!), s.log, "log_enc decrypts to the log");

    const listing = fromSpecJson<ListingValues>(issue.listing);
    assert.deepEqual(listing.values, { game: "MDGP", season: 1, frames: 6170, log_h: logH, price: "0.1", seller: "0123456789abcdef", book: s.rec.book, human: true });
    assert.deepEqual(listing.flags, { readonly: true, permissionlessExtension: false });
    assert.deepEqual(listing.expiry, { kind: "days", days: 7 });

    assert.deepEqual([s.arkiv.batches.length, s.arkiv.runs.length, s.arkiv.listings.length, s.arkiv.stamps.length], [0, 0, 0, 0], "nothing written");
    assert.equal(s.store.approvalFor(JTI)?.log_h, logH, "the approval is bound to this log before anything goes out");
  });

  it("written with the approved wallet's entities: one stamp by the checker naming the run and the wallet; done carries stamp and stamp_tx", async () => {
    const s = setup();
    s.approve(JTI);
    const v = await publish(s);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.deepEqual(Object.keys(v.data).sort(), ["listing", "replay", "run", "stamp", "stamp_tx", "tx"]);
    const run = s.arkiv.runs[0];
    const listing = s.arkiv.listings[0];
    assert.deepEqual([run.creator, listing.creator, listing.run], [WALLET_A, WALLET_A, run.key], "the console's wallet created both");
    assert.deepEqual([v.data.run, v.data.listing, v.data.tx], [run.key, listing.key, s.arkiv.consoleTxs[0].tx]);

    assert.equal(s.arkiv.stamps.length, 1);
    const st = s.arkiv.stamps[0];
    assert.equal(st.creator, CHECKER);
    assert.deepEqual(st.spec.values, {
      run: run.key,
      console: WALLET_A,
      game: "MDGP",
      season: 1,
      frames: 6170,
      log_h: sha256(s.log),
      book: s.rec.book,
      human: true,
      final_hash: 576543229,
      tool: "arcade_replay sha256:a992006e6280",
    });
    assert.deepEqual(st.spec.flags, STAMP_FLAGS);
    // Season end + 30 d (T0 + 60 d here) is 2,592,000 two-second blocks after the fake chain's block 1,000,000.
    assert.deepEqual(st.spec.expiry, { kind: "atBlock", block: 3_592_000n }, "the stamp expires with its run");
    assert.deepEqual(s.arkiv.batches.map((b) => b.kind), ["stamp"]);
    assert.deepEqual([v.data.stamp, v.data.stamp_tx], [st.key, s.arkiv.batches[0].tx]);
    assert.deepEqual(s.store.approvalFor(JTI)?.result, { run: run.key, listing: listing.key, tx: v.data.tx, stamp: st.key, stamp_tx: v.data.stamp_tx });
  });

  it("the stamp copies the run's lap splits", async () => {
    const s = setup({ splits: new FakeSplits() });
    s.approve(JTI);
    assert.equal((await publish(s)).ok, true);
    const rv = s.arkiv.runs[0].spec.values;
    const st = s.arkiv.stamps[0].spec.values;
    assert.deepEqual([rv.s1, rv.s2, rv.s3, rv.split_kind], [2087, 1995, 2088, "lap"]);
    assert.deepEqual([st.s1, st.s2, st.s3, st.s4, st.split_kind], [2087, 1995, 2088, undefined, "lap"]);
  });

  it("human and credential come from the book (Selfie Check here)", async () => {
    const s = setup();
    linkWallet(s.store, s.other.book, WALLET_B);
    s.approve("jti-other", s.other.book);
    const v = await publish(s, { book: s.other.book, jti: "jti-other" }, WALLET_B);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(s.arkiv.runs[0].spec.values.credential, "Selfie Check");
    assert.equal(s.arkiv.runs[0].spec.values.runner, "fedcba9876543210");
    assert.equal(s.arkiv.stamps[0].spec.values.console, WALLET_B);
  });

  it("logs keys and the time but never the jti, the log or a secret", async () => {
    const s = setup();
    s.approve(JTI);
    const v = await publish(s);
    const all = s.lines.join("\n");
    assert.match(all, new RegExp(`arkiv publish ${s.rec.book} MDGP 1:42\\.83: issued to the console`));
    assert.match(all, new RegExp(`arkiv publish ${s.rec.book} MDGP 1:42\\.83: run ${String(v.data.run)} listing ${String(v.data.listing)} stamp ${String(v.data.stamp)}`));
    for (const bad of [JTI, s.body().log as string, GHOST, SECRET]) assert.ok(!all.includes(bad), "leaked");
  });

  it("the done view says what this job's replay gave: the frames and the final hash as the tool printed it", async () => {
    const s = setup();
    s.approve(JTI);
    const v = await publish(s);
    assert.equal(s.checker.calls, 1);
    assert.deepEqual(v.data.replay, { frames: 6170, final_hash: 576543229 });
    assert.equal(typeof (v.data.replay as { final_hash: unknown }).final_hash, "number", "sent as it is, not as hex");

    const t = setup();
    t.checker.result = { final_hash: undefined }; // a tool that printed no final hash
    t.approve(JTI);
    const w = await publish(t);
    assert.deepEqual(w.data.replay, { frames: 6170, final_hash: null });
    assert.equal("final_hash" in t.arkiv.stamps[0].spec.values, false, "no final_hash column then");
  });

  it("stages: check while replaying, sign while the console writes, write while the stamp is out, then done", async () => {
    const s = setup();
    s.approve(JTI);
    let release!: () => void;
    s.arkiv.holdWrites = new Promise<void>((r) => (release = r));
    const { id } = s.pub.start(s.body());
    assert.equal(s.pub.view(id)!.stage, "check");
    await waitFor(() => s.pub.view(id)!.stage === "sign");
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(s.pub.view(id)!));
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    await waitFor(() => s.pub.view(id)!.stage === "write");
    assert.deepEqual(s.pub.view(id), { stage: "write", ok: null, failure: null, data: {} });
    release();
    assert.equal((await finish(s.pub, id)).ok, true);
  });
});

describe("publish: only the World-approved wallet's runs are stamped (Review Focus 2)", () => {
  it("entities from another wallet (a reflashed console, a new key): ls_not_linked, no stamp", async () => {
    const s = setup();
    s.approve(JTI);
    const v = await publish(s, {}, WALLET_B);
    assert.deepEqual([v.ok, v.failure], [false, "ls_not_linked"]);
    assert.equal(s.arkiv.stamps.length, 0);
    assert.match(s.lines.join("\n"), /ls_not_linked \(the run was created by 0xb2b2…b2b2, not a wallet linked to this book\)/);
  });

  it("no console of the book has an approved wallet: ls_not_linked before anything is issued; once linked the same approval goes through", async () => {
    const s = setup({ link: false });
    s.approve(JTI);
    const { view } = await issued(s);
    assert.deepEqual([view.stage, view.failure], ["done", "ls_not_linked"]);
    assert.equal(view.data.issue, undefined, "nothing issued");
    assert.equal(s.store.approvalFor(JTI)?.log_h, undefined, "not spent");
    linkWallet(s.store, s.rec.book, WALLET_A);
    const v = await publish(s);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(s.arkiv.stamps.length, 1);
  });

  it("a wallet linked to another book does not count", async () => {
    const s = setup({ link: false });
    linkWallet(s.store, s.other.book, WALLET_A);
    s.approve(JTI);
    assert.equal((await issued(s)).view.failure, "ls_not_linked");
  });

  it("the listing from another linked wallet than its run: ls_publish_fail, no stamp", async () => {
    const s = setup();
    linkWallet(s.store, s.rec.book, WALLET_B); // the book's second console
    s.approve(JTI);
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    s.arkiv.listings[0].creator = WALLET_B;
    s.pub.written(id, w);
    const v = await finish(s.pub, id);
    assert.deepEqual([v.failure, s.arkiv.stamps.length], ["ls_publish_fail", 0]);
  });
});

describe("publish: the console's entities must be exactly what was issued", () => {
  const cases: Array<[string, Parameters<FakeArkiv["consoleWrite"]>[2], ((s: S) => void)?]> = [
    ["another time", { run: (v) => (v.frames = 6169) }],
    ["human off", { run: (v) => (v.human = false) }],
    ["no credential", { run: (v) => delete v.credential }],
    ["a column it was not issued", { run: (v) => (v.gen = "hand-made") }],
    ["a ghost that does not decrypt to this log", { run: (v) => (v.log_enc = new Uint8Array(80)) }],
    ["the plain log as well", { run: (v) => (v.log = new Uint8Array(40)) }],
    ["another price", { listing: (v) => (v.price = "0.2") }],
    ["a payout account it was not approved for", { listing: (v) => (v.pay_to = "0.0.666") }],
    ["a listing naming another run", {}, (s) => (s.arkiv.listings[0].run = `0x${"9".repeat(64)}`)],
    ["a run that can be edited", {}, (s) => (s.arkiv.runs[0].spec.flags = { readonly: false, permissionlessExtension: true })],
    ["a run handed to another owner", {}, (s) => (s.arkiv.runs[0].owner = WALLET_B)],
  ];
  for (const [what, edit, after] of cases) {
    it(`${what}: ls_publish_fail, no stamp`, async () => {
      const s = setup();
      s.approve(JTI);
      const { id, view } = await issued(s);
      const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view), edit);
      after?.(s);
      s.pub.written(id, w);
      const v = await finish(s.pub, id);
      assert.deepEqual([v.ok, v.failure], [false, "ls_publish_fail"], what);
      assert.equal(s.arkiv.stamps.length, 0);
    });
  }

  it("a node that has not seen the block yet: asked again, then stamped", async () => {
    const s = setup();
    s.approve(JTI);
    s.arkiv.lagEntityReads = 2;
    assert.equal((await publish(s)).ok, true);
    assert.equal(s.arkiv.stamps.length, 1);
  });

  it("keys that are not on Arkiv: ls_publish_fail; the console's report with the right keys then stamps", async () => {
    const s = setup();
    s.approve(JTI);
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    s.pub.written(id, { ...w, run: `0x${"7".repeat(64)}` });
    const v = await finish(s.pub, id);
    assert.equal(v.failure, "ls_publish_fail");
    assert.match(s.lines.join("\n"), /the run is not on Arkiv/);
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    await waitFor(() => s.pub.view(id)?.ok === true);
    assert.equal(s.arkiv.stamps.length, 1);
  });
});

describe("written: the console's report", () => {
  it("written twice: one stamp, the same answer (Review Focus 5)", async () => {
    const s = setup();
    s.approve(JTI);
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    assert.deepEqual(s.pub.written(id, w), { ok: true }, "a repeat while it stamps");
    const v = await finish(s.pub, id);
    assert.equal(v.ok, true);
    assert.deepEqual(s.pub.written(id, w), { ok: true }, "a repeat after done");
    assert.deepEqual(s.pub.view(id), v);
    assert.equal(s.arkiv.stamps.length, 1);
  });

  it("404 for an unknown job, 400 for a bad body, 409 before the sign stage or for other keys after done", async () => {
    const s = setup();
    s.approve(JTI);
    const refused = (fn: () => unknown) => {
      try {
        fn();
        return "ok";
      } catch (e) {
        assert.ok(e instanceof PublishRefused);
        return `${e.status} ${e.error}`;
      }
    };
    const key = (c: string) => `0x${c.repeat(64)}`;
    const good = { tx: key("a"), run: key("b"), listing: key("c") };
    assert.equal(refused(() => s.pub.written("nope", good)), "404 unknown_id");
    const { id } = s.pub.start(s.body());
    assert.equal(refused(() => s.pub.written(id, good)), "409 not_signing", "still checking");
    await waitFor(() => s.pub.view(id)?.stage === "sign");
    for (const bad of [{}, { ...good, tx: "0x12" }, { ...good, run: "b".repeat(64) }, { ...good, listing: 7 }, { ...good, run: good.listing }]) {
      assert.equal(refused(() => s.pub.written(id, bad)), "400 bad_body", JSON.stringify(bad));
    }
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(s.pub.view(id)!));
    s.pub.written(id, w);
    await finish(s.pub, id);
    assert.equal(refused(() => s.pub.written(id, { ...w, listing: key("d") })), "409 not_signing");
  });

  it("the stamp write fails: ls_publish_fail; the console's written again stamps it (the records already exist)", async () => {
    const s = setup();
    s.approve(JTI);
    s.arkiv.failWrites = 1;
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    s.pub.written(id, w);
    assert.equal((await finish(s.pub, id)).failure, "ls_publish_fail");
    assert.match(s.lines.join("\n"), /stamp write: reverted/);
    assert.equal(s.arkiv.stamps.length, 0);
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    await waitFor(() => s.pub.view(id)?.ok === true);
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length], [1, 1], "the console signed once");
  });

  it("the stamp write times out; when it lands later, the retry answers its keys", async () => {
    const s = setup();
    s.approve(JTI);
    let release!: () => void;
    s.arkiv.holdWrites = new Promise<void>((r) => (release = r));
    const v = await publish(s);
    assert.equal(v.failure, "ls_publish_fail");
    assert.match(s.lines.join("\n"), /stamp write timed out/);
    release();
    s.arkiv.holdWrites = null;
    await waitFor(() => s.store.approvalFor(JTI)?.result !== undefined);
    const again = await finish(s.pub, s.pub.start(s.body()).id);
    assert.equal(again.ok, true, JSON.stringify(again));
    assert.equal(again.data.stamp, s.arkiv.stamps[0].key);
    assert.equal(s.arkiv.stamps.length, 1, "stamped once");
  });
});

describe("publish: retries", () => {
  it("the console's transaction landed but it was never told (a timeout): the retry finds the entities by log_h, checks them and stamps once (Review Focus 5)", async () => {
    const s = setup();
    s.approve(JTI);
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view)); // landed; the console's signer gave up waiting
    const again = s.pub.start(s.body());
    assert.equal(again.id, id);
    const v = await finish(s.pub, id);
    assert.equal(v.ok, true, JSON.stringify(v));
    // The re-run built a fresh log_enc (a new nonce); the landed run's own one is checked by decrypting it.
    assert.deepEqual([v.data.run, v.data.listing, v.data.tx], [w.run, w.listing, null]);
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length], [1, 1], "nothing signed twice, stamped once");
    // The console's late report: the same answer, now with its transaction.
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    assert.equal(s.pub.view(id)?.data.tx, w.tx);
    assert.equal(s.arkiv.stamps.length, 1);
  });

  it("a repeat POST while the job waits at sign and nothing landed: the same id, issued again", async () => {
    const s = setup();
    s.approve(JTI);
    const { id } = await issued(s);
    const again = s.pub.start(s.body());
    assert.equal(again.id, id);
    const v = await consoleFinish(s.pub, s.arkiv, id);
    assert.equal(v.ok, true);
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length, s.checker.calls], [1, 1, 2]);
  });

  it("after success and after the job is forgotten, the same jti answers the same keys and stamp without a write", async () => {
    const s = setup();
    s.approve(JTI);
    const v1 = await publish(s);
    s.clock.ms += 3_600_001;
    const v2 = await finish(s.pub, s.pub.start(s.body()).id);
    const { replay, ...keys } = v1.data;
    assert.ok(replay, "the first job replayed the log");
    // Answered from the approval's record, not replayed again: no replay in its view.
    assert.deepEqual(v2, { ...v1, data: keys });
    assert.equal(s.checker.calls, 1);
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length], [1, 1]);
  });

  it("a duplicate under the same book with a live listing: the existing keys and stamp, nothing issued", async () => {
    const s = setup();
    s.approve(JTI);
    const v1 = await publish(s);
    s.approve("second-approval");
    const { view: v2 } = await issued(s, { jti: "second-approval" });
    assert.equal(v2.ok, true, JSON.stringify(v2));
    assert.deepEqual([v2.data.run, v2.data.listing, v2.data.stamp], [v1.data.run, v1.data.listing, v1.data.stamp]);
    assert.deepEqual(v2.data.replay, { frames: 6170, final_hash: 576543229 }, "this job replayed the log too");
    assert.equal(s.checker.calls, 2);
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length], [1, 1]);
  });

  it("a duplicate under the same book whose listing ended: a listing only, for the stamped run, from its wallet; no new stamp", async () => {
    const s = setup();
    s.approve(JTI);
    const v1 = await publish(s);
    s.arkiv.listings[0].live = false; // its 7 days ran out
    s.approve("second-approval");
    const { id, view } = await issued(s, { jti: "second-approval" });
    assert.equal(view.stage, "sign");
    const issue = issueOf(view);
    assert.deepEqual([issue.run, issue.run_key, issue.replaces], [null, v1.data.run, null]);
    const v2 = await consoleFinish(s.pub, s.arkiv, id);
    assert.equal(v2.ok, true, JSON.stringify(v2));
    assert.equal(v2.data.run, v1.data.run);
    assert.notEqual(v2.data.listing, v1.data.listing);
    assert.equal(v2.data.stamp, v1.data.stamp);
    assert.equal(s.arkiv.listings[1].run, v1.data.run);
    assert.deepEqual(s.arkiv.consoleTxs.map((t) => t.creates), [2, 1]);
    assert.equal(s.arkiv.stamps.length, 1);
  });

  it("a relist must name the stamped run, and comes from the run's own wallet", async () => {
    const s = setup();
    s.approve(JTI);
    await publish(s);
    s.arkiv.listings[0].live = false;
    s.approve("second-approval");
    const { id, view } = await issued(s, { jti: "second-approval" });
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    assert.throws(() => s.pub.written(id, { ...w, run: `0x${"5".repeat(64)}` }), (e: unknown) => e instanceof PublishRefused && e.status === 400);
    // The book's wallet changed since the run was stamped (A released, B linked): no listing for A's run.
    const t = setup({ link: false });
    const consoleA = linkWallet(t.store, t.rec.book, WALLET_A);
    t.approve(JTI);
    await publish(t);
    t.arkiv.listings[0].live = false;
    t.store.setConsole(consoleA, { book: null, state: "released", by: "release", wallet: null }, 1);
    linkWallet(t.store, t.rec.book, WALLET_B);
    t.approve("second-approval");
    assert.equal((await issued(t, { jti: "second-approval" })).view.failure, "ls_not_linked");
  });

  it("two approvals for one log at once: one stamp; the other answers its keys", async () => {
    const s = setup();
    s.approve("a-1");
    s.approve("a-2");
    const [a, b] = [s.pub.start(s.body({ jti: "a-1" })), s.pub.start(s.body({ jti: "a-2" }))];
    const [va, vb] = [await consoleFinish(s.pub, s.arkiv, a.id), await consoleFinish(s.pub, s.arkiv, b.id)];
    assert.equal(va.ok && vb.ok, true, JSON.stringify([va, vb]));
    assert.deepEqual([vb.data.run, vb.data.stamp], [va.data.run, va.data.stamp]);
    assert.equal(s.arkiv.stamps.length, 1);
  });

  it("jobs are forgotten an hour after they were made", async () => {
    const s = setup();
    s.approve(JTI);
    const { id } = s.pub.start(s.body());
    await consoleFinish(s.pub, s.arkiv, id);
    s.clock.ms += 3_600_001;
    s.pub.start(s.body({ jti: "another" })); // any start prunes
    assert.equal(s.pub.view(id), undefined);
  });
});

describe("publish: every failure row", () => {
  it("ls_expired: an approval unknown to this bridge", async () => {
    const s = setup();
    assert.equal((await publish(s)).failure, "ls_expired");
    assert.equal(s.arkiv.consoleTxs.length, 0);
  });

  it("ls_expired: an unspent approval more than 24 h old", async () => {
    const s = setup();
    s.approve(JTI);
    s.clock.ms += DAY + 1000;
    assert.equal((await publish(s)).failure, "ls_expired");
  });

  it("ls_wrong: approved for another book", async () => {
    const s = setup();
    s.approve(JTI, s.other.book);
    assert.equal((await publish(s)).failure, "ls_wrong");
  });

  it("ls_wrong: a book this bridge never issued", async () => {
    const s = setup();
    s.approve(JTI, "ANY-ZZZ");
    assert.equal((await publish(s, { book: "ANY-ZZZ" })).failure, "ls_wrong");
  });

  it("ls_copied: the same log already stamped under another book (a copied run, not a wrong World ID); nothing issued, nothing spent", async () => {
    const s = setup();
    // The same log, listed and stamped under the other book first.
    linkWallet(s.store, s.other.book, WALLET_B);
    s.approve("theirs", s.other.book);
    assert.equal((await publish(s, { jti: "theirs", book: s.other.book }, WALLET_B)).ok, true);
    s.approve(JTI);
    const { view } = await issued(s);
    assert.equal(view.failure, "ls_copied");
    assert.equal(view.data.issue, undefined);
    assert.equal(s.store.approvalFor(JTI)?.log_h, undefined, "not spent");
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length], [1, 1]);
  });

  it("ls_mismatch: the text differs from what World App showed (its hash)", async () => {
    const s = setup();
    s.approve(JTI, s.rec.book, "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC");
    assert.equal((await publish(s)).failure, "ls_mismatch");
  });

  it("ls_mismatch: the approved title is not this request's title", async () => {
    const s = setup();
    const text = actionText("RUSH HOUR", 6170, 10);
    s.approve(JTI, s.rec.book, text);
    assert.equal((await publish(s, { action: text })).failure, "ls_mismatch");
  });

  it("ls_mismatch: the replayed time is not the time asked", async () => {
    const s = setup({ frames: 6169 });
    s.approve(JTI);
    assert.equal((await publish(s)).failure, "ls_mismatch");
    assert.match(s.lines.join("\n"), /replayed 1:42\.82, asked 1:42\.83/);
  });

  it("ls_mismatch: the approved time is not the replayed time (frames and text both off)", async () => {
    const s = setup({ frames: 6290 });
    s.approve(JTI);
    assert.equal((await publish(s, { frames: 6290 })).failure, "ls_mismatch");
  });

  it("ls_mismatch: the price differs", async () => {
    const s = setup();
    const text = actionText(TITLE, 6170, 20);
    s.approve(JTI, s.rec.book, text);
    assert.equal((await publish(s, { price_c: 20, action: text })).failure, "ls_mismatch");
  });

  it("ls_mismatch: the log's header names another game", async () => {
    const s = setup();
    s.approve(JTI);
    assert.equal((await publish(s, { log: Buffer.from(makeLog("RUSH")).toString("base64") })).failure, "ls_mismatch");
    assert.equal(s.checker.calls, 0, "never replayed");
  });

  it("ls_reused: the approval already put another run on Arkiv", async () => {
    const s = setup();
    s.approve(JTI);
    assert.equal((await publish(s)).ok, true);
    const other = Buffer.from(makeLog("MDGP", 4, 6461, 64, 9)).toString("base64");
    const s2 = s.pub.start(s.body({ log: other }));
    // The first job is held and succeeded, so the same jti answers its id; a new body is a new job only once it is gone.
    assert.equal((await finish(s.pub, s2.id)).ok, true);
    s.clock.ms += 3_600_001;
    const v = await finish(s.pub, s.pub.start(s.body({ log: other })).id);
    assert.equal(v.failure, "ls_reused");
    assert.deepEqual([s.arkiv.stamps.length, s.arkiv.consoleTxs.length], [1, 1]);
  });

  it("ls_publish_fail: the replay refuses the log", async () => {
    for (const bad of [{ hash_matches: false }, { complete: false }, { claims_match: false }, { finished: false }, { game: "RUSH" }]) {
      const s = setup();
      s.checker.result = bad;
      s.approve(JTI);
      assert.equal((await publish(s)).failure, "ls_publish_fail", JSON.stringify(bad));
      assert.equal(s.arkiv.consoleTxs.length, 0);
    }
  });

  it("ls_publish_fail: the tool errors or times out (logged with the reason)", async () => {
    for (const r of ["error", "timeout"] as const) {
      const s = setup();
      s.checker.result = r;
      s.approve(JTI);
      assert.equal((await publish(s)).failure, "ls_publish_fail");
      assert.match(s.lines.join("\n"), /replay tool: (exit 2|timed out)/);
    }
  });

  it("ls_publish_fail: Arkiv down at the dedupe read", async () => {
    const s = setup();
    s.arkiv.readsDown = true;
    s.approve(JTI);
    assert.equal((await publish(s)).failure, "ls_publish_fail");
  });

  it("ls_publish_fail: Arkiv down when the console's entities are read back; the console's written again stamps", async () => {
    const s = setup();
    s.approve(JTI);
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    s.arkiv.readsDown = true;
    s.pub.written(id, w);
    assert.equal((await finish(s.pub, id)).failure, "ls_publish_fail");
    s.arkiv.readsDown = false;
    s.pub.written(id, w);
    await waitFor(() => s.pub.view(id)?.ok === true);
    assert.equal(s.arkiv.stamps.length, 1);
  });
});

describe("publish: the body (400 bad_body) and the gate (503)", () => {
  const base = setup().body();
  const cases: Array<[string, Record<string, unknown>]> = [
    ["no book", { book: undefined }],
    ["a book that is not ANY-XXX", { book: "ANY_6PS" }],
    ["no jti", { jti: "" }],
    ["a control character in the action", { action: "List\nx" }],
    ["an action over 160", { action: "x".repeat(161) }],
    ["an unknown game", { game: "DOOM" }],
    ["a title over 64 bytes", { title: "M".repeat(65) }],
    ["frames not an integer", { frames: 61.5 }],
    ["price not an integer", { price_c: "10" }],
    ["log not base64", { log: "not base64!" }],
    ["a log under 32 bytes", { log: Buffer.alloc(31).toString("base64") }],
    ["a log over 64 KiB", { log: Buffer.from(makeLog("MDGP", 4, 1, 64 * 1024)).toString("base64") }],
    ["a log that is not ACL1", { log: Buffer.alloc(64, 1).toString("base64") }],
  ];
  for (const [what, over] of cases) {
    it(what, () => {
      assert.throws(() => parseBody({ ...base, ...over }), (e: unknown) => e instanceof PublishRefused && e.status === 400 && e.error === "bad_body");
    });
  }

  it("a well-formed body parses: log_h, rules and the header's game", () => {
    const p = parseBody(base);
    assert.equal(p.logH.length, 64);
    assert.equal(p.rules, 4);
    assert.equal(p.headerGame, "MDGP");
  });

  it("the gate refuses a new job with 503 and its reason", () => {
    const s = setup();
    for (const reason of ["arkiv_not_configured", "arkiv_unavailable"] as const) {
      const pub = new Publisher({ arkiv: s.arkiv, checker: s.checker, store: s.store, season: 1, runExpiry: new Date(T0 + DAY), priceC: 10, ghostSecret: GHOST, chainId: CHAIN, rpc: RPC, gate: () => reason });
      assert.throws(() => pub.start(s.body()), (e: unknown) => e instanceof PublishRefused && e.status === 503 && e.error === reason);
    }
  });

  it("the bridge never writes a run or a listing: the console's wallet creates both, the checker only the stamp", async () => {
    const s = setup();
    s.approve(JTI);
    await publish(s);
    assert.ok([...s.arkiv.runs, ...s.arkiv.listings].every((r) => r.creator === WALLET_A));
    assert.ok(s.arkiv.stamps.every((r) => r.creator === CHECKER));
    assert.ok(s.arkiv.batches.every((b) => b.kind === "stamp"));
  });
});

describe("publish: the stamp follows what was issued (Task 1 review follow-ups)", () => {
  it("the stamp never outlives the run as issued: stamped at the earlier of the run's own expiry and the issued one", async () => {
    for (const [runBlock, stampBlock] of [
      [9_000_000n, 3_592_000n], // the console pushed its run out to the chain's maximum: the stamp stays at season end + 30 d
      [2_000_000n, 2_000_000n], // a run that ends earlier takes its stamp with it
    ]) {
      const s = setup();
      s.approve(JTI);
      const { id, view } = await issued(s);
      const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
      s.arkiv.expiresAt.set(w.run, runBlock);
      s.pub.written(id, w);
      assert.equal((await finish(s.pub, id)).ok, true);
      assert.deepEqual(s.arkiv.stamps[0].spec.expiry, { kind: "atBlock", block: stampBlock }, String(runBlock));
    }
  });

  it("a run or listing whose owner or flags the node does not report, or that carries a payload, is not what was issued: nothing stamped", async () => {
    const cases: Array<[string, "run" | "listing", (a: FakeArkiv, key: string) => void]> = [
      ["its owner", "run", (a, k) => a.entityEdit.set(k, { owner: null })],
      ["its flags", "run", (a, k) => a.entityEdit.set(k, { flags: null })],
      ["its payload", "run", (a, k) => a.payloadOn.add(k)],
      ["its owner", "listing", (a, k) => a.entityEdit.set(k, { owner: null })],
      ["its flags", "listing", (a, k) => a.entityEdit.set(k, { flags: null })],
      ["its payload", "listing", (a, k) => a.payloadOn.add(k)],
    ];
    for (const [what, which, edit] of cases) {
      const s = setup();
      s.approve(JTI);
      const { id, view } = await issued(s);
      const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
      edit(s.arkiv, which === "run" ? w.run : w.listing);
      s.pub.written(id, w);
      const v = await finish(s.pub, id);
      assert.equal(v.failure, "ls_publish_fail", `${which} ${what}`);
      assert.ok(s.lines.join("\n").includes(`the ${which} on Arkiv is not the one issued (${what})`), s.lines.join("\n"));
      assert.equal(s.arkiv.stamps.length, 0);
    }
  });

  it("a stamp write that errs after its transaction landed: the stamp is looked up before failing and answers; no second stamp", async () => {
    const s = setup();
    s.approve(JTI);
    s.arkiv.failAfterLanding = 1;
    const v = await publish(s);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(s.arkiv.stamps.length, 1);
    assert.deepEqual([v.data.stamp, v.data.stamp_tx], [s.arkiv.stamps[0].key, null]);
    assert.equal(s.store.approvalFor(JTI)?.result?.stamp, s.arkiv.stamps[0].key);
  });

  it("written again once the approval records the stamp (a node that does not show it yet): answered from the record, never a second stamp", async () => {
    const s = setup();
    s.approve(JTI);
    let release!: () => void;
    s.arkiv.holdWrites = new Promise<void>((r) => (release = r));
    const { id, view } = await issued(s);
    const w = s.arkiv.consoleWrite(WALLET_A, issueOf(view));
    s.pub.written(id, w);
    assert.equal((await finish(s.pub, id)).failure, "ls_publish_fail", "the stamp write timed out");
    release();
    s.arkiv.holdWrites = null;
    await waitFor(() => s.store.approvalFor(JTI)?.result?.stamp !== undefined);
    s.arkiv.lagStampReads = 10;
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    await waitFor(() => s.pub.view(id)?.ok === true);
    assert.equal(s.arkiv.stamps.length, 1, "one stamp");
    assert.equal(s.pub.view(id)?.data.stamp, s.arkiv.stamps[0].key);
  });

  it("a relist that replaces a listing is done only once that listing is gone", async () => {
    const s = setup();
    s.approve(JTI);
    const first = await publish(s);
    assert.equal(first.ok, true);
    const ACCT = "0.0.5123456";
    s.store.setPayto(s.rec.book, ACCT, 1);
    const text = actionText(TITLE, 6170, 10, ACCT);
    s.approve("jti-relist", s.rec.book, text);
    const { id, view } = await issued(s, { jti: "jti-relist", action: text, pay_to: ACCT });
    const issue = issueOf(view);
    assert.deepEqual([issue.run, issue.run_key, issue.replaces], [null, first.data.run, first.data.listing]);
    const w = s.arkiv.consoleWrite(WALLET_A, issue, { keepReplaced: true }); // the console left the old listing live
    s.pub.written(id, w);
    assert.equal((await finish(s.pub, id)).failure, "ls_publish_fail");
    assert.match(s.lines.join("\n"), /the listing it replaces is still live/);
    s.arkiv.listings.find((l) => l.key === first.data.listing)!.live = false; // now it is gone
    assert.deepEqual(s.pub.written(id, w), { ok: true });
    await waitFor(() => s.pub.view(id)?.ok === true);
    assert.equal(s.pub.view(id)?.data.listing, w.listing);
    assert.equal(s.arkiv.stamps.length, 1, "a relist writes no stamp");
  });
});
