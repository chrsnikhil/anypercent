/** POST /arkiv/publish's pipeline against a fake Arkiv, a fake checker and a fake clock. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { describe, it } from "node:test";
import { decryptGhost } from "../src/arkiv/ghost.js";
import { actionText, fmtTime, parseBody, priceDec, priceText, PublishRefused, Publisher, type PublishView } from "../src/arkiv/publish.js";
import { nullifierKey } from "../src/hmac.js";
import { Store } from "../src/store.js";
import { CHECKER, FakeArkiv, FakeChecker, makeLog } from "./fake-arkiv.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const GHOST = "ab".repeat(32);
const TITLE = "MARINE DRIVE GP";
const T0 = 1_800_000_000_000;
const DAY = 86_400_000;
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const sha256 = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");

let seq = 0;

function setup(opts: { frames?: number; priceC?: number } = {}) {
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
    now: () => clock.ms,
    log: (l) => lines.push(l),
    writeTimeoutMs: 200,
  });
  const action = actionText(TITLE, 6170, 10);
  /** A fresh approval for this book (as the approval providers record it). */
  const approve = (jti: string, book = rec.book, text = action) => store.recordApproval(jti, book, sha(text), Math.floor(clock.ms / 1000));
  const log = makeLog("MDGP");
  const body = (over: Record<string, unknown> = {}) => ({
    book: rec.book,
    jti: "3f9c0a1b2c3d4e5f",
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

async function finish(pub: Publisher, id: string): Promise<PublishView> {
  await waitFor(() => pub.view(id)?.stage === "done");
  return pub.view(id)!;
}

async function publish(s: ReturnType<typeof setup>, over: Record<string, unknown> = {}): Promise<PublishView> {
  const { id, expires_s } = s.pub.start(s.body(over));
  assert.equal(expires_s, 120);
  return finish(s.pub, id);
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

describe("publish: happy path", () => {
  it("writes the run and its listing in one batch, with every column, the flags and the expiry", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const v = await publish(s);
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(v.failure, null);
    assert.deepEqual(Object.keys(v.data).sort(), ["listing", "run", "tx"]);
    assert.equal(s.arkiv.batches.length, 1);
    assert.equal(s.arkiv.batches[0].kind, "run+listing");
    assert.equal(v.data.tx, s.arkiv.batches[0].tx);

    const run = s.arkiv.runs[0];
    assert.equal(v.data.run, run.key);
    const rv = run.spec.values;
    const logH = sha256(s.log);
    assert.deepEqual(
      { ...rv, log_enc: undefined },
      {
        game: "MDGP",
        title: TITLE,
        season: 1,
        rules: 4,
        frames: 6170,
        log_h: logH,
        runner: "0123456789abcdef",
        book: s.rec.book,
        human: true,
        credential: "Orb",
        tool: "arcade_replay sha256:a992006e6280",
        log_enc: undefined,
      },
    );
    assert.equal(rv.log, undefined, "a listed run never carries the plain log");
    assert.equal(rv.label, undefined, "a World-tier run has no label");
    assert.deepEqual(run.spec.flags, { readonly: true, permissionlessExtension: true });
    assert.deepEqual(run.spec.expiry, { kind: "atDate", date: new Date(T0 + 60 * DAY), atLeastDays: 1 });
    assert.ok(rv.log_enc instanceof Uint8Array);
    assert.deepEqual(decryptGhost(GHOST, logH, rv.log_enc!), s.log, "log_enc decrypts to the log");

    const listing = s.arkiv.listings[0];
    assert.equal(v.data.listing, listing.key);
    assert.equal(listing.run, run.key, "the listing names the run's key");
    assert.deepEqual(listing.spec.values, {
      game: "MDGP",
      season: 1,
      frames: 6170,
      log_h: logH,
      price: "0.1",
      seller: "0123456789abcdef",
      book: s.rec.book,
      human: true,
    });
    assert.deepEqual(listing.spec.flags, { readonly: true, permissionlessExtension: false });
    assert.deepEqual(listing.spec.expiry, { kind: "days", days: 7 });
  });

  it("human and credential come from the book (Selfie Check here)", async () => {
    const s = setup();
    s.approve("jti-other", s.other.book);
    const v = await publish(s, { book: s.other.book, jti: "jti-other" });
    assert.equal(v.ok, true);
    assert.equal(s.arkiv.runs[0].spec.values.credential, "Selfie Check");
    assert.equal(s.arkiv.runs[0].spec.values.runner, "fedcba9876543210");
    assert.equal(s.arkiv.runs[0].spec.values.human, true);
  });

  it("binds the approval to the log, and logs keys and the time but never the jti, the log or a secret", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const v = await publish(s);
    assert.equal(s.store.approvalFor("3f9c0a1b2c3d4e5f")?.log_h, sha256(s.log));
    const all = s.lines.join("\n");
    assert.match(all, new RegExp(`arkiv publish ${s.rec.book} MDGP 1:42\\.83: run ${String(v.data.run)} listing ${String(v.data.listing)}`));
    for (const bad of ["3f9c0a1b2c3d4e5f", s.body().log as string, GHOST, SECRET]) assert.ok(!all.includes(bad), "leaked");
  });

  it("stages: check while replaying, write while the transaction is out, then done", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    let release!: () => void;
    s.arkiv.holdWrites = new Promise<void>((r) => (release = r));
    const { id } = s.pub.start(s.body());
    assert.equal(s.pub.view(id)!.stage, "check");
    await waitFor(() => s.pub.view(id)!.stage === "write");
    assert.deepEqual(s.pub.view(id), { stage: "write", ok: null, failure: null, data: {} });
    release();
    assert.equal((await finish(s.pub, id)).ok, true);
  });
});

describe("publish: every failure row", () => {
  it("ls_expired: an approval unknown to this bridge", async () => {
    const s = setup();
    assert.equal((await publish(s)).failure, "ls_expired");
    assert.equal(s.arkiv.batches.length, 0);
  });

  it("ls_expired: an unspent approval more than 24 h old", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    s.clock.ms += DAY + 1000;
    assert.equal((await publish(s)).failure, "ls_expired");
  });

  it("ls_wrong: approved for another book", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f", s.other.book);
    assert.equal((await publish(s)).failure, "ls_wrong");
  });

  it("ls_wrong: a book this bridge never issued", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f", "ANY-ZZZ");
    assert.equal((await publish(s, { book: "ANY-ZZZ" })).failure, "ls_wrong");
  });

  it("ls_copied: the same log already on the board under another book (a copied run, not a wrong World ID)", async () => {
    const s = setup();
    s.arkiv.addRun({ game: "MDGP", title: TITLE, season: 1, rules: 4, frames: 6170, log_h: sha256(s.log), runner: "fedcba9876543210", book: s.other.book, human: true, credential: "Orb", tool: "t", log_enc: new Uint8Array(40) });
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s)).failure, "ls_copied");
    assert.equal(s.arkiv.batches.length, 0);
    assert.equal(s.store.approvalFor("3f9c0a1b2c3d4e5f")?.log_h, undefined, "not spent");
  });

  it("ls_mismatch: the text differs from what World App showed (its hash)", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f", s.rec.book, "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC");
    assert.equal((await publish(s)).failure, "ls_mismatch");
  });

  it("ls_mismatch: the approved title is not this request's title", async () => {
    const s = setup();
    const text = actionText("RUSH HOUR", 6170, 10);
    s.approve("3f9c0a1b2c3d4e5f", s.rec.book, text);
    assert.equal((await publish(s, { action: text })).failure, "ls_mismatch");
  });

  it("ls_mismatch: the replayed time is not the time asked", async () => {
    const s = setup({ frames: 6169 });
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s)).failure, "ls_mismatch");
    assert.match(s.lines.join("\n"), /replayed 1:42\.82, asked 1:42\.83/);
  });

  it("ls_mismatch: the approved time is not the replayed time (frames and text both off)", async () => {
    const s = setup({ frames: 6290 });
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s, { frames: 6290 })).failure, "ls_mismatch");
  });

  it("ls_mismatch: the price differs", async () => {
    const s = setup();
    const text = actionText(TITLE, 6170, 20);
    s.approve("3f9c0a1b2c3d4e5f", s.rec.book, text);
    assert.equal((await publish(s, { price_c: 20, action: text })).failure, "ls_mismatch");
  });

  it("ls_mismatch: the log's header names another game", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s, { log: Buffer.from(makeLog("RUSH")).toString("base64") })).failure, "ls_mismatch");
    assert.equal(s.checker.calls, 0, "never replayed");
  });

  it("ls_reused: the approval already put another run on Arkiv", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s)).ok, true);
    const other = Buffer.from(makeLog("MDGP", 4, 6461, 64, 9)).toString("base64");
    const s2 = s.pub.start(s.body({ log: other }));
    // The first job is held and succeeded, so the same jti answers its id; a new body is a new job only once it is gone.
    assert.equal((await finish(s.pub, s2.id)).ok, true);
    s.clock.ms += 3_600_001;
    const v = await finish(s.pub, s.pub.start(s.body({ log: other })).id);
    assert.equal(v.failure, "ls_reused");
    assert.equal(s.arkiv.batches.length, 1);
  });

  it("ls_publish_fail: the replay refuses the log", async () => {
    for (const bad of [{ hash_matches: false }, { complete: false }, { claims_match: false }, { finished: false }, { game: "RUSH" }]) {
      const s = setup();
      s.checker.result = bad;
      s.approve("3f9c0a1b2c3d4e5f");
      assert.equal((await publish(s)).failure, "ls_publish_fail", JSON.stringify(bad));
      assert.equal(s.arkiv.batches.length, 0);
    }
  });

  it("ls_publish_fail: the tool errors or times out (logged with the reason)", async () => {
    for (const r of ["error", "timeout"] as const) {
      const s = setup();
      s.checker.result = r;
      s.approve("3f9c0a1b2c3d4e5f");
      assert.equal((await publish(s)).failure, "ls_publish_fail");
      assert.match(s.lines.join("\n"), /replay tool: (exit 2|timed out)/);
    }
  });

  it("ls_publish_fail: Arkiv down at the dedupe read", async () => {
    const s = setup();
    s.arkiv.readsDown = true;
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s)).failure, "ls_publish_fail");
  });

  it("ls_publish_fail: a reverted write", async () => {
    const s = setup();
    s.arkiv.failWrites = 1;
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s)).failure, "ls_publish_fail");
    assert.match(s.lines.join("\n"), /Arkiv write: reverted/);
  });

  it("ls_publish_fail: a write that times out; when it lands later, the retry answers its keys", async () => {
    const s = setup();
    let release!: () => void;
    s.arkiv.holdWrites = new Promise<void>((r) => (release = r));
    s.approve("3f9c0a1b2c3d4e5f");
    assert.equal((await publish(s)).failure, "ls_publish_fail");
    release();
    s.arkiv.holdWrites = null;
    await waitFor(() => s.store.approvalFor("3f9c0a1b2c3d4e5f")?.result !== undefined);
    const v = await publish(s);
    assert.equal(v.ok, true);
    assert.equal(v.data.run, s.arkiv.runs[0].key);
    assert.equal(s.arkiv.batches.length, 1, "written once");
  });
});

describe("publish: retries", () => {
  it("a repeat POST with the same jti answers the same id while the job is held", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const a = s.pub.start(s.body());
    const b = s.pub.start(s.body());
    assert.equal(a.id, b.id);
    await finish(s.pub, a.id);
    assert.equal(s.pub.start(s.body()).id, a.id);
    assert.equal(s.arkiv.batches.length, 1);
  });

  it("after a failed write, the retry with the same jti goes through (same id), written once", async () => {
    const s = setup();
    s.arkiv.failWrites = 1;
    s.approve("3f9c0a1b2c3d4e5f");
    const first = s.pub.start(s.body());
    assert.equal((await finish(s.pub, first.id)).failure, "ls_publish_fail");
    assert.equal(s.store.approvalFor("3f9c0a1b2c3d4e5f")?.log_h, sha256(s.log), "the binding is kept");
    const again = s.pub.start(s.body());
    assert.equal(again.id, first.id);
    const v = await finish(s.pub, again.id);
    assert.equal(v.ok, true);
    assert.equal(s.arkiv.batches.length, 1);
  });

  it("after success and after the job is forgotten, the same jti answers the same keys without a write", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const v1 = await publish(s);
    s.clock.ms += 3_600_001;
    const v2 = await publish(s);
    assert.deepEqual(v2, v1);
    assert.equal(s.arkiv.batches.length, 1);
  });

  it("a duplicate under the same book with a live listing: the existing keys, nothing written", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const v1 = await publish(s);
    s.approve("second-approval");
    const v2 = await publish(s, { jti: "second-approval" });
    assert.equal(v2.ok, true);
    assert.equal(v2.data.run, v1.data.run);
    assert.equal(v2.data.listing, v1.data.listing);
    assert.equal(s.arkiv.batches.length, 1);
  });

  it("a duplicate under the same book whose listing ended: a listing only, for the same run", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const v1 = await publish(s);
    s.arkiv.listings[0].live = false; // its 7 days ran out
    s.approve("second-approval");
    const v2 = await publish(s, { jti: "second-approval" });
    assert.equal(v2.ok, true);
    assert.equal(v2.data.run, v1.data.run);
    assert.notEqual(v2.data.listing, v1.data.listing);
    assert.deepEqual(s.arkiv.batches.map((b) => b.kind), ["run+listing", "listing"]);
    assert.equal(s.arkiv.listings[1].run, v1.data.run);
  });

  it("a duplicate under another book: ls_copied", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    await publish(s);
    s.approve("theirs", s.other.book);
    assert.equal((await publish(s, { jti: "theirs", book: s.other.book })).failure, "ls_copied");
    assert.equal(s.arkiv.batches.length, 1);
  });

  it("two approvals for one log at once: one run is written, the other answers its keys", async () => {
    const s = setup();
    s.approve("a-1");
    s.approve("a-2");
    const [a, b] = [s.pub.start(s.body({ jti: "a-1" })), s.pub.start(s.body({ jti: "a-2" }))];
    const [va, vb] = [await finish(s.pub, a.id), await finish(s.pub, b.id)];
    assert.equal(va.ok && vb.ok, true);
    assert.equal(va.data.run, vb.data.run);
    assert.equal(s.arkiv.runs.length, 1);
  });

  it("jobs are forgotten an hour after they were made", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    const { id } = s.pub.start(s.body());
    await finish(s.pub, id);
    s.clock.ms += 3_600_001;
    s.pub.start(s.body({ jti: "another" })); // any start prunes
    assert.equal(s.pub.view(id), undefined);
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
      const pub = new Publisher({ arkiv: s.arkiv, checker: s.checker, store: s.store, season: 1, runExpiry: new Date(T0 + DAY), priceC: 10, ghostSecret: GHOST, gate: () => reason });
      assert.throws(() => pub.start(s.body()), (e: unknown) => e instanceof PublishRefused && e.status === 503 && e.error === reason);
    }
  });

  it("the checker is the only writer: every row the fake holds is the checker's", async () => {
    const s = setup();
    s.approve("3f9c0a1b2c3d4e5f");
    await publish(s);
    assert.ok([...s.arkiv.runs, ...s.arkiv.listings].every((r) => r.creator === CHECKER));
  });
});
