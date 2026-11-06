/**
 * The Arkiv changes the Hedera module brings: the listing's optional pay_to and hcs columns, the
 * approved text with "to <pay_to>", the payout registry (data/payto.json), a relist that puts an old
 * listing up for sale, old rows still reading, the web board, and /arkiv/ghost under Hedera payments.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { describe, it } from "node:test";
import { encryptGhost, sha256Hex } from "../src/arkiv/ghost.js";
import { MockPayments } from "../src/arkiv/payments.js";
import { actionText, parseBody, PublishRefused, Publisher, type PublishView } from "../src/arkiv/publish.js";
import { LISTING_ATTRS } from "../src/arkiv/queries.js";
import { decodeRow } from "../src/arkiv/rows.js";
import { LISTING_TYPES } from "../src/arkiv/schema.js";
import { ArkivService, RouteError } from "../src/arkiv/service.js";
import { HederaPayments } from "../src/hedera/payments.js";
import { nullifierKey } from "../src/hmac.js";
import { Store } from "../src/store.js";
import { CHECKER, consoleFinish, FakeArkiv, FakeChecker, linkWallet, makeLog, WALLET_A } from "./fake-arkiv.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const GHOST = "ab".repeat(32);
const TITLE = "MARINE DRIVE GP";
const ACCT = "0.0.5123456";
const sha = (s: string) => createHash("sha256").update(s).digest("hex");

let seq = 0;
function setup() {
  seq += 1;
  const dir = tempDir();
  const store = new Store(dir, SECRET);
  const rec = store.claimBook(nullifierKey(SECRET, "act", `hk-${seq}`), "Orb", "0123456789abcdef", 1, "session_x").record;
  const arkiv = new FakeArkiv();
  const pub = new Publisher({ arkiv, checker: new FakeChecker(6170), store, season: 1, runExpiry: new Date(Date.now() + 60 * 86_400_000), priceC: 10, ghostSecret: GHOST, chainId: 7794095, rpc: "https://rpc.example", writeTimeoutMs: 200, verifyGapMs: 1 });
  linkWallet(store, rec.book, WALLET_A);
  const log = makeLog("MDGP", 4, 6461, 64, 500 + seq);
  const approve = (jti: string, text: string) => store.recordApproval(jti, rec.book, sha(text), Math.floor(Date.now() / 1000));
  const body = (over: Record<string, unknown> = {}) => ({
    book: rec.book,
    jti: "jti-a",
    action: actionText(TITLE, 6170, 10, ACCT),
    game: "MDGP",
    title: TITLE,
    frames: 6170,
    price_c: 10,
    pay_to: ACCT,
    log: Buffer.from(log).toString("base64"),
    ...over,
  });
  /** The whole listing: the checks, the console signing from its linked wallet, the stamp. */
  const publish = async (over: Record<string, unknown> = {}): Promise<PublishView> => consoleFinish(pub, arkiv, pub.start(body(over)).id);
  return { dir, store, rec, arkiv, pub, log, approve, body, publish };
}

describe("the approved text names the payout account", () => {
  it("with and without pay_to", () => {
    assert.equal(actionText(TITLE, 6170, 10), "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC on the public board");
    assert.equal(actionText(TITLE, 6170, 10, ACCT), "List MARINE DRIVE GP 1:42.83 ghost for 0.10 USDC to 0.0.5123456 on the public board");
    assert.equal(actionText(TITLE, 6170, 10, null), actionText(TITLE, 6170, 10));
  });

  it("the publish body takes an optional pay_to (0.0.N only)", () => {
    const s = setup();
    assert.equal(parseBody(s.body()).pay_to, ACCT);
    assert.equal(parseBody(s.body({ pay_to: undefined })).pay_to, undefined);
    assert.equal(parseBody(s.body({ pay_to: null })).pay_to, undefined);
    for (const bad of ["0x1234567890123456789012345678901234567890", "0.0.", "1.2.3", 5, "0.0.12345678901"]) {
      assert.throws(() => parseBody(s.body({ pay_to: bad })), PublishRefused, String(bad));
    }
  });
});

describe("publish with a payout account", () => {
  it("the listing row carries pay_to and hcs (the LISTING message of this approval)", async () => {
    const s = setup();
    s.store.setPayto(s.rec.book, ACCT, 1);
    s.approve("jti-a", actionText(TITLE, 6170, 10, ACCT));
    s.store.setHcsListing("jti-a", { topic: "0.0.8001", tx: "0.0.7001@1800000000.000000001", seq: "41" });
    const v = await s.publish();
    assert.equal(v.ok, true, JSON.stringify(v));
    const l = s.arkiv.listings[0].spec.values;
    assert.equal(l.pay_to, ACCT);
    assert.equal(l.hcs, "0.0.8001/41");
  });

  it("no LISTING (Hedera off): the row has pay_to and no hcs; publish never needs one", async () => {
    const s = setup();
    s.store.setPayto(s.rec.book, ACCT, 1);
    s.approve("jti-a", actionText(TITLE, 6170, 10, ACCT));
    s.store.setHcsListing("jti-a", { topic: "0.0.8001", tx: "0.0.7001@1800000000.000000001" });
    assert.equal((await s.publish()).ok, true);
    assert.equal(s.arkiv.listings[0].spec.values.hcs, undefined);
  });

  it("a book with no account lists as before: no 'to', no pay_to", async () => {
    const s = setup();
    const plain = actionText(TITLE, 6170, 10);
    s.approve("jti-a", plain);
    const v = await s.publish({ action: plain, pay_to: undefined });
    assert.equal(v.ok, true, JSON.stringify(v));
    assert.equal(s.arkiv.listings[0].spec.values.pay_to, undefined);
  });

  it("pay_to that is not the book's registered account: ls_mismatch (either way round)", async () => {
    const s = setup();
    s.approve("jti-a", actionText(TITLE, 6170, 10, ACCT));
    assert.equal((await s.publish()).failure, "ls_mismatch", "registry empty, body names one");

    const s2 = setup();
    s2.store.setPayto(s2.rec.book, "0.0.999", 1);
    s2.approve("jti-a", actionText(TITLE, 6170, 10, ACCT));
    assert.equal((await s2.publish()).failure, "ls_mismatch", "registry names another");

    const s3 = setup();
    s3.store.setPayto(s3.rec.book, ACCT, 1);
    const plain = actionText(TITLE, 6170, 10);
    s3.approve("jti-a", plain);
    assert.equal((await s3.publish({ action: plain, pay_to: undefined })).failure, "ls_mismatch", "registry names one, body none");
    assert.deepEqual([s3.arkiv.batches.length, s3.arkiv.consoleTxs.length], [0, 0]);
  });

  it("a relist with a payout account replaces the run's old listing (no pay_to) in the console's one transaction; the run keeps its stamp", async () => {
    const s = setup();
    const plain = actionText(TITLE, 6170, 10);
    s.approve("jti-old", plain);
    const first = await s.publish({ jti: "jti-old", action: plain, pay_to: undefined });
    assert.equal(first.ok, true);
    const oldListing = first.data.listing;
    s.store.setPayto(s.rec.book, ACCT, 1);
    s.approve("jti-new", actionText(TITLE, 6170, 10, ACCT));
    const second = await s.publish({ jti: "jti-new" });
    assert.equal(second.ok, true, JSON.stringify(second));
    assert.equal(second.data.run, first.data.run);
    assert.notEqual(second.data.listing, oldListing);
    assert.equal(second.data.stamp, first.data.stamp);
    assert.deepEqual(s.arkiv.consoleTxs.map((t) => [t.creates, t.deletes]), [[2, 0], [1, 1]]);
    assert.deepEqual(s.arkiv.batches.map((b) => b.kind), ["stamp"], "one stamp for the run");
    assert.equal(s.arkiv.listings.find((l) => l.key === oldListing)?.live, false, "the old listing went in the same transaction");
    assert.equal(s.arkiv.listings.filter((l) => l.live).length, 1);
    assert.equal(s.arkiv.listings.find((l) => l.live)?.spec.values.pay_to, ACCT);
  });

  it("a relist with the same pay_to answers the live listing, writing nothing", async () => {
    const s = setup();
    s.store.setPayto(s.rec.book, ACCT, 1);
    s.approve("jti-a", actionText(TITLE, 6170, 10, ACCT));
    const first = await s.publish();
    s.approve("jti-b", actionText(TITLE, 6170, 10, ACCT));
    const second = await s.publish({ jti: "jti-b" });
    assert.equal(second.data.listing, first.data.listing);
    assert.deepEqual([s.arkiv.batches.length, s.arkiv.consoleTxs.length], [1, 1]);
  });
});

describe("old rows and the readers", () => {
  const K = `0x${"1a".repeat(32)}`;
  const listingRaw = (extra: Array<{ name: string; type: string; value: unknown }> = []) => ({
    key: `0x${"2b".repeat(32)}`,
    creator: CHECKER,
    expiresAt: "0x10",
    attributes: [
      { name: "arkiv.schema", type: "str", value: "anypercent.listing" },
      { name: "run", type: "bytes32", value: K },
      { name: "game", type: "str", value: "MDGP" },
      { name: "season", type: "i32", value: 1 },
      { name: "frames", type: "u64", value: "0x181a" },
      { name: "log_h", type: "str", value: "f".repeat(64) },
      { name: "price", type: "dec", value: "0.1" },
      { name: "seller", type: "str", value: "0123456789abcdef" },
      { name: "book", type: "str", value: "ANY-6PS" },
      { name: "human", type: "bool", value: true },
      ...extra,
    ],
  });

  it("a listing written before pay_to/hcs still reads; a new one reads both", () => {
    assert.ok(LISTING_ATTRS.includes("pay_to") && LISTING_ATTRS.includes("hcs"));
    assert.deepEqual([LISTING_TYPES.pay_to, LISTING_TYPES.hcs], [{ type: "str", required: false }, { type: "str", required: false }]);
    const old = decodeRow(listingRaw(), LISTING_TYPES, LISTING_ATTRS, "anypercent.listing", CHECKER);
    assert.ok("row" in old && old.row.values.pay_to === undefined);
    const fresh = decodeRow(listingRaw([{ name: "pay_to", type: "str", value: ACCT }, { name: "hcs", type: "str", value: "0.0.8001/41" }]), LISTING_TYPES, LISTING_ATTRS, "anypercent.listing", CHECKER);
    assert.ok("row" in fresh && fresh.row.values.pay_to === ACCT && fresh.row.values.hcs === "0.0.8001/41");
    const mistyped = decodeRow(listingRaw([{ name: "pay_to", type: "u64", value: "0x1" }]), LISTING_TYPES, LISTING_ATTRS, "anypercent.listing", CHECKER);
    assert.ok("dropped" in mistyped);
  });

  it("the web board reads both columns as optional and links them on HashScan", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    const js = html.split("<script>")[1].split("</script>")[0].split("// ---- State")[0];
    const page = runInNewContext(`${js}\n;({ decodeAll, LISTING_TYPES, LISTING_REQUIRED, LISTING_ATTRS, CHECKER, ACCOUNT_RE, HCS_RE })`, { BigInt, Number, document: {}, location: {} }) as any;
    assert.ok(!page.LISTING_REQUIRED.includes("pay_to") && !page.LISTING_REQUIRED.includes("hcs"));
    assert.ok(page.LISTING_ATTRS.includes("pay_to") && page.LISTING_ATTRS.includes("hcs"));
    const pin = page.CHECKER;
    const withCols = { ...listingRaw([{ name: "pay_to", type: "str", value: ACCT }, { name: "hcs", type: "str", value: "0.0.8001/41" }]), creator: pin.toLowerCase() };
    const old = { ...listingRaw(), creator: pin.toLowerCase() };
    const out = page.decodeAll([withCols, old], page.LISTING_TYPES, page.LISTING_REQUIRED, "anypercent.listing", pin);
    assert.equal(out.dropped, 0);
    assert.equal(out.rows[0].pay_to, ACCT);
    assert.equal(out.rows[1].pay_to, undefined);
    assert.ok(page.ACCOUNT_RE.test(ACCT) && page.HCS_RE.test("0.0.8001/41") && !page.HCS_RE.test("0.0.8001"));
    assert.ok(html.includes("pays ${l.pay_to}") && html.includes("approved on Hedera") && html.includes("https://hashscan.io/testnet"));
  });

  it("the web board links each run, and a listed run's listing, on the Arkiv explorer", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    const js = html.split("<script>")[1].split("</script>")[0].split("// ---- State")[0];
    const page = runInNewContext(`${js}\n;({ entityUrl, EXPLORER })`, { BigInt, Number, document: {}, location: {} }) as {
      entityUrl: (key: unknown) => string | null;
      EXPLORER: string;
    };
    const run = "0x" + "12ab".repeat(16);
    assert.equal(page.EXPLORER, "https://rabdi.explorer.arkiv.network");
    assert.equal(page.entityUrl(run), `${page.EXPLORER}/entity/${run}`); // as the service's explorer_entity builds it
    for (const odd of [undefined, null, 7, "", "0x12", run + "00", run.toUpperCase(), `../${run}`]) assert.equal(page.entityUrl(odd), null, String(odd));
    const body = html.split("// ---- State")[1];
    assert.ok(body.includes('"on Arkiv"') && body.includes('"listing"') && body.includes("arkivLinks(meta, r)"));
    assert.ok(/hederaLinks\(meta, r\.listing\);\s*\n\s*arkivLinks\(meta, r\);/.test(body), "next to the Hedera links");
  });
});

describe("the payout registry (data/payto.json)", () => {
  it("the CLI's write is seen by a running service's store, without touching state.json", () => {
    const s = setup();
    const before = readFileSync(join(s.dir, "state.json"), "utf8");
    const cli = new Store(s.dir, SECRET);
    assert.equal(s.store.paytoFor(s.rec.book), undefined);
    cli.setPayto(s.rec.book, ACCT, 5);
    assert.equal(s.store.paytoFor(s.rec.book), ACCT);
    cli.setPayto(s.rec.book, null, 6);
    assert.equal(s.store.paytoFor(s.rec.book), undefined);
    assert.equal(readFileSync(join(s.dir, "state.json"), "utf8"), before);
  });
});

describe("/arkiv/ghost under Hedera payments", () => {
  function svcWith(payments: ConstructorParameters<typeof ArkivService>[0]["payments"], arkiv: FakeArkiv, lines: string[]) {
    return new ArkivService({ publicRpc: "https://rpc.example", chainId: 7794095, season: 1, priceC: 10, checker: CHECKER, arkiv, publisher: null, payments, ghostSecret: GHOST, problems: [], boardFile: "x", snapshotFile: "x", log: (l) => lines.push(l) });
  }
  function listed(arkiv: FakeArkiv) {
    const log = makeLog("MDGP", 4, 6170, 64, 77);
    const logH = sha256Hex(log);
    return arkiv.addRun({ game: "MDGP", title: TITLE, season: 1, rules: 4, frames: 6170, log_h: logH, runner: "0123456789abcdef", book: "ANY-6PS", human: true, credential: "Orb", tool: "t", log_enc: encryptGhost(GHOST, logH, log) });
  }

  it("a settled sale's transaction unlocks its run (either id form), not another; mock receipts are refused, logged once", async () => {
    const store = new Store(tempDir(), SECRET);
    const arkiv = new FakeArkiv();
    const run = listed(arkiv);
    const other = listed(arkiv);
    const lines: string[] = [];
    const svc = svcWith(new HederaPayments(store, null, (l) => lines.push(l)), arkiv, lines);
    const tx = "0.0.9185802@1800000000.000000123";
    store.recordSale(tx, { run, listing: `0x${"9".repeat(64)}`, seller: "ANY-6PS", game: "MDGP", pay_to: ACCT, amount: "100000", asset: "0.0.429274", payer: "0.0.6001234", buyer: null, at: 1 });
    assert.ok((await svc.ghost({ run, receipt: tx })).log);
    assert.ok((await svc.ghost({ run, receipt: "0.0.9185802-1800000000-000000123" })).log);
    await assert.rejects(svc.ghost({ run: other, receipt: tx }), (e: unknown) => e instanceof RouteError && e.status === 402);
    await assert.rejects(svc.ghost({ run, receipt: "mock-1a2b3c4d" }), (e: unknown) => e instanceof RouteError && e.status === 402);
    await assert.rejects(svc.ghost({ run, receipt: "mock-1a2b3c4e" }), (e: unknown) => e instanceof RouteError && e.status === 402);
    assert.equal(lines.filter((l) => l.includes("mock receipts are refused")).length, 1);
  });

  it("with Hedera payments off, mock receipts still work as before (ARKIV_MOCK_PAYMENTS=1)", async () => {
    const store = new Store(tempDir(), SECRET);
    const arkiv = new FakeArkiv();
    const run = listed(arkiv);
    const svc = svcWith(new MockPayments(true, store), arkiv, []);
    assert.ok((await svc.ghost({ run, receipt: "mock-1a2b3c4d" })).log);
  });
});
