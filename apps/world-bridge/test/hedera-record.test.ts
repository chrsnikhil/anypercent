/** POST /hedera/record: the LISTING message, every failure, one LISTING per approval. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, describe, it } from "node:test";
import { actionText } from "../src/arkiv/publish.js";
import { RecordRefused, type RecordView } from "../src/hedera/record.js";
import { CHECKER, STRANGER } from "./fake-arkiv.js";
import { SELLER_ACCT, TOPIC } from "./fake-hedera.js";
import { hedera, type Harness } from "./hedera-harness.js";
import { waitFor } from "./helpers.js";

const open: Harness[] = [];
after(async () => {
  for (const h of open) await h.close();
});

const TITLE = "MARINE DRIVE GP";
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const nowS = () => Math.floor(Date.now() / 1000);

async function setup() {
  const h = await hedera();
  open.push(h);
  const action = actionText(TITLE, 6170, 10, SELLER_ACCT);
  const approve = (jti: string, book = h.seller.book, text = action, at = nowS()) => h.store.recordApproval(jti, book, sha(text), at);
  const body = (over: Record<string, unknown> = {}) => ({ book: h.seller.book, jti: "jti-0001", action, game: "MDGP", title: TITLE, frames: 6170, price_c: 10, pay_to: SELLER_ACCT, ...over });
  const record = async (over: Record<string, unknown> = {}): Promise<RecordView & { id: string }> => {
    const { id, expires_s } = h.recorder.start(body(over));
    assert.equal(expires_s, 120);
    await waitFor(() => h.recorder.view(id)?.stage === "done", 5000);
    return { ...h.recorder.view(id)!, id };
  };
  return { h, action, approve, body, record };
}

describe("record: the LISTING", () => {
  it("puts the approved listing on the topic, word for word, and answers {topic, seq, tx, hashscan}", async () => {
    const s = await setup();
    s.approve("jti-0001");
    const v = await s.record();
    assert.equal(v.ok, true, JSON.stringify(v));
    const [m] = s.h.hcs.of("LISTING");
    assert.equal(m.topic, TOPIC);
    assert.equal(
      Buffer.from(m.bytes).toString("utf8"),
      `{"v":1,"t":"LISTING","book":"${s.h.seller.book}","runner":"1111222233334444","game":"MDGP","frames":6170,"price":"0.10","pay_to":"${SELLER_ACCT}","action":"List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC to ${SELLER_ACCT} on the public board"}`,
    );
    assert.deepEqual(v.data, {
      topic: TOPIC,
      seq: 1,
      tx: m.tx,
      hashscan: `https://hashscan.io/testnet/transaction/${m.tx.replace("@", "-").replace(/\.(\d{9})$/, "-$1")}`,
      hashscan_topic: `https://hashscan.io/testnet/topic/${TOPIC}`,
    });
    assert.equal(s.h.store.hcsListingFor("jti-0001")?.seq, "1");
    assert.ok(!s.h.lines.join("\n").includes("jti-0001"), "the jti is never logged");
  });

  it("a book with no payout account lists without pay_to", async () => {
    const s = await setup();
    s.h.store.setPayto(s.h.seller.book, null, 2);
    const plain = actionText(TITLE, 6170, 10);
    s.approve("jti-plain", s.h.seller.book, plain);
    const v = await s.record({ jti: "jti-plain", action: plain, pay_to: undefined });
    assert.equal(v.ok, true);
    assert.ok(!Buffer.from(s.h.hcs.of("LISTING")[0].bytes).toString().includes("pay_to"));
  });

  it("the same jti answers the same id, and puts one LISTING on the topic", async () => {
    const s = await setup();
    s.approve("jti-0001");
    const a = await s.record();
    const again = s.h.recorder.start(s.body());
    assert.equal(again.id, a.id);
    assert.equal(s.h.hcs.of("LISTING").length, 1);
  });

  it("the record does not spend the approval", async () => {
    const s = await setup();
    s.approve("jti-0001");
    await s.record();
    assert.equal(s.h.store.approvalFor("jti-0001")?.log_h, undefined);
  });
});

describe("record: failures", () => {
  it("ls_expired: approval unknown, or unspent and over 24 h", async () => {
    const s = await setup();
    assert.equal((await s.record()).failure, "ls_expired");
    s.approve("jti-old", s.h.seller.book, s.action, nowS() - 25 * 3600);
    assert.equal((await s.record({ jti: "jti-old" })).failure, "ls_expired");
  });

  it("ls_wrong: approved for another book, or a book not issued here", async () => {
    const s = await setup();
    s.approve("jti-0001", s.h.buyer.book);
    assert.equal((await s.record()).failure, "ls_wrong");
    s.approve("jti-nope", "ANY-NOPE");
    assert.equal((await s.record({ jti: "jti-nope", book: "ANY-NOPE" })).failure, "ls_wrong");
  });

  it("ls_mismatch: text hash, price, the rendered text, pay_to against the registry", async () => {
    const s = await setup();
    s.approve("jti-0001");
    assert.equal((await s.record({ action: `${s.action} ` })).failure, "ls_mismatch");
    const p20 = actionText(TITLE, 6170, 20, SELLER_ACCT);
    s.approve("jti-p20", s.h.seller.book, p20);
    assert.equal((await s.record({ jti: "jti-p20", action: p20, price_c: 20 })).failure, "ls_mismatch");
    s.approve("jti-title", s.h.seller.book, s.action);
    assert.equal((await s.record({ jti: "jti-title", title: "RUSH HOUR" })).failure, "ls_mismatch");
    const other = actionText(TITLE, 6170, 10, "0.0.999");
    s.approve("jti-acct", s.h.seller.book, other);
    assert.equal((await s.record({ jti: "jti-acct", action: other, pay_to: "0.0.999" })).failure, "ls_mismatch");
    const none = actionText(TITLE, 6170, 10);
    s.approve("jti-none", s.h.seller.book, none);
    assert.equal((await s.record({ jti: "jti-none", action: none, pay_to: undefined })).failure, "ls_mismatch", "the book has an account: the text must name it");
    assert.equal(s.h.hcs.messages.length, 0);
  });

  it("ls_reused: the approval was already spent with no LISTING for it", async () => {
    const s = await setup();
    s.approve("jti-0001");
    s.h.store.spendApproval("jti-0001", "a".repeat(64));
    assert.equal((await s.record()).failure, "ls_reused");
  });

  it("ls_copied: this log is already on the board under another book; nothing goes to the topic", async () => {
    const s = await setup();
    const plain = actionText(TITLE, 6170, 10);
    s.approve("jti-copy", s.h.buyer.book, plain);
    const v = await s.record({ book: s.h.buyer.book, jti: "jti-copy", action: plain, pay_to: undefined, log_h: s.h.logH });
    assert.equal(v.failure, "ls_copied");
    assert.equal(s.h.hcs.messages.length, 0);
    assert.equal(s.h.store.hcsListingFor("jti-copy"), undefined);
    assert.equal(s.h.store.approvalFor("jti-copy")?.log_h, undefined, "not spent");
    assert.ok(s.h.lines.some((l) => l.includes("ls_copied (this log is already on the board under another book)")), s.h.lines.join("\n"));
  });

  it("ls_copied reads the stamps: a copied log of a console-owned run is refused before its LISTING; a run no stamp names is no copy", async () => {
    const s = await setup();
    const plain = actionText(TITLE, 6170, 10);
    // The harness's run is the seller console's own (WALLET_A), stamped by the checker: on the board.
    assert.notEqual(s.h.arkiv.runs[0].creator, CHECKER);
    assert.ok(s.h.arkiv.stamps.some((st) => st.spec.values.run === s.h.run));
    s.approve("jti-copy", s.h.buyer.book, plain);
    assert.equal((await s.record({ book: s.h.buyer.book, jti: "jti-copy", action: plain, pay_to: undefined, log_h: s.h.logH })).failure, "ls_copied");
    assert.equal(s.h.hcs.of("LISTING").length, 0, "no LISTING for a copy");
    // A run of another log under another book that no checker stamp names (a stranger's, an old checker row): not on the board.
    const loose = "c".repeat(64);
    s.h.arkiv.addRun({ ...s.h.arkiv.runs[0].spec.values, log_h: loose }, STRANGER, { stamp: false });
    s.h.arkiv.addRun({ ...s.h.arkiv.runs[0].spec.values, log_h: loose }, CHECKER, { stamp: false });
    s.approve("jti-loose", s.h.buyer.book, plain);
    assert.equal((await s.record({ book: s.h.buyer.book, jti: "jti-loose", action: plain, pay_to: undefined, log_h: loose })).ok, true);
  });

  it("the copy check passes the book's own run and a log not on the board", async () => {
    const s = await setup();
    s.approve("jti-0001");
    assert.equal((await s.record({ log_h: s.h.logH })).ok, true, "its own run: a relist");
    s.approve("jti-new");
    assert.equal((await s.record({ jti: "jti-new", log_h: "c".repeat(64) })).ok, true, "a new run");
    assert.equal(s.h.hcs.of("LISTING").length, 2);
  });

  it("Arkiv unreadable at the copy check: ls_record_fail, nothing goes to the topic", async () => {
    const s = await setup();
    s.approve("jti-0001");
    s.h.arkiv.readsDown = true;
    const v = await s.record({ log_h: s.h.logH });
    assert.equal(v.failure, "ls_record_fail");
    assert.equal(s.h.hcs.messages.length, 0);
    assert.ok(s.h.lines.some((l) => l.includes("copy check")), s.h.lines.join("\n"));
  });

  it("no log_h (an older console): no copy check, recorded as before", async () => {
    const s = await setup();
    s.approve("jti-0001");
    s.h.arkiv.readsDown = true;
    assert.equal((await s.record()).ok, true);
  });

  it("ls_record_fail: HCS refused it", async () => {
    const s = await setup();
    s.approve("jti-0001");
    s.h.hcs.refuse = 1;
    const v = await s.record();
    assert.equal(v.failure, "ls_record_fail");
    assert.ok(s.h.lines.some((l) => l.includes("HCS refused it: INVALID_TOPIC_ID")));
  });

  it("ls_record_fail on a receipt timeout; the retry reuses the message once it landed", async () => {
    const s = await setup();
    s.approve("jti-0001");
    s.h.hcs.holdReceipts = true;
    const first = await s.record();
    assert.equal(first.failure, "ls_record_fail");
    s.h.hcs.land();
    s.h.hcs.holdReceipts = false;
    await waitFor(() => s.h.store.hcsListingFor("jti-0001")?.seq !== undefined);
    const second = await s.record();
    assert.equal(second.id, first.id);
    assert.equal(second.ok, true);
    assert.equal(s.h.hcs.of("LISTING").length, 1, "one approval, one LISTING");
  });

  it("a bad body is 400, an unknown id 404 (ls_record_fail)", async () => {
    const s = await setup();
    assert.throws(() => s.h.recorder.start({ ...s.body(), pay_to: "0x1234" }), (e: unknown) => e instanceof RecordRefused && e.status === 400);
    assert.throws(() => s.h.recorder.start({ ...s.body(), frames: 0 }), RecordRefused);
    for (const log_h of ["AB".repeat(32), "ab".repeat(31), "ab".repeat(33), 7]) {
      assert.throws(() => s.h.recorder.start({ ...s.body(), log_h }), (e: unknown) => e instanceof RecordRefused && e.status === 400, String(log_h));
    }
    const res = await fetch(`${s.h.base}/hedera/record`, { method: "POST", body: "{" });
    assert.deepEqual([res.status, await res.json()], [400, { error: "bad_body", failure: "ls_record_fail" }]);
    const big = await fetch(`${s.h.base}/hedera/record`, { method: "POST", body: JSON.stringify({ pad: "x".repeat(5000) }) });
    assert.deepEqual([big.status, await big.json()], [400, { error: "bad_body", failure: "ls_record_fail" }]);
    const unknown = await fetch(`${s.h.base}/hedera/record/nope`);
    assert.deepEqual([unknown.status, await unknown.json()], [404, { error: "unknown_id", failure: "ls_record_fail" }]);
  });
});
