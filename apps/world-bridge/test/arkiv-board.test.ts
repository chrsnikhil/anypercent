/**
 * Every reader ranks stamped runs only (spec: Entities, console-owned records): the join itself
 * (board.ts), the real port's board, run and listing reads against a node stub that honours the
 * creator pins, and the web board's own copy of the rule (public/board.html, run here in a VM on the
 * same raw rows).
 *
 * The five-row mix every reader must agree on:
 *   K1  a run of WALLET_A stamped by the checker naming WALLET_A        kept
 *   K2  a run of WALLET_A that no stamp names                           dropped (never on a board)
 *   K3  a run of WALLET_B whose stamp names WALLET_A                    dropped
 *   K4  a run whose stamp copied other frames                           dropped
 *   L2  a stranger's listing naming K1                                  dropped (L1, WALLET_A's, kept)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { getAddress, keccak256 as viemKeccak, toBytes } from "viem";
import { joinBoard } from "../src/arkiv/board.js";
import { SdkArkiv, type ListingRow, type RunRow, type StampRow } from "../src/arkiv/client.js";
import * as Q from "../src/arkiv/queries.js";
import { COLUMN_DEFS, type EntityKind } from "../src/arkiv/schema.js";
import { STRANGER, WALLET_A, WALLET_B } from "./fake-arkiv.js";

const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const C = "0x8ba1f109551bD432803012645Ac136ddd64DBA72";
const k = (n: number) => `0x${String(n).padStart(2, "0").repeat(32)}`;
const H = (n: number) => String(n).repeat(64).slice(0, 64);
const [K1, K2, K3, K4, L1, L2, S1, S3, S4] = [11, 12, 13, 14, 21, 22, 31, 33, 34].map(k);

// ---- the rows, as values -------------------------------------------------------------------------

const runV = (frames: number, logH: string) => ({ game: "MDGP", title: "MARINE DRIVE GP", season: 1, rules: 4, frames, log_h: logH, runner: "0123456789abcdef", book: "ANY-6PS", human: true, credential: "Orb", tool: "t", s1: 2087, s2: 1995, s3: frames - 4082, split_kind: "lap" });
const stampV = (run: string, wallet: string, frames: number, logH: string) => ({ run, console: wallet, game: "MDGP", season: 1, frames, log_h: logH, book: "ANY-6PS", human: true, s1: 2087, s2: 1995, s3: frames - 4082, split_kind: "lap", tool: "t" });
const listingV = (run: string, frames: number, logH: string) => ({ run, game: "MDGP", season: 1, frames, log_h: logH, price: "0.1", seller: "0123456789abcdef", book: "ANY-6PS", human: true, pay_to: "0.0.5123456" });

/** A row as arkiv_query answers it: typed attributes (u64 as 0x quantities, a key column tagged bytes32 as Rabdi does). */
function raw(kind: EntityKind, schema: string, key: string, creator: string, values: Record<string, unknown>) {
  const attributes: Array<{ name: string; type: string; value: unknown }> = [{ name: "arkiv.schema", type: "str", value: schema }];
  for (const [name, v] of Object.entries(values)) {
    const t = COLUMN_DEFS[kind][name].type;
    attributes.push({ name, type: t === "key" ? "bytes32" : t, value: t === "u64" ? `0x${Number(v).toString(16)}` : v });
  }
  return { key, creator: creator.toLowerCase(), expiresAt: "0x41eee8", attributes };
}

function rawMix(checker: string) {
  const stamps = [
    raw("stamp", "anypercent.stamp", S4, checker, stampV(K4, WALLET_A, 6100, H(4))),
    raw("stamp", "anypercent.stamp", S1, checker, stampV(K1, WALLET_A, 6170, H(1))),
    raw("stamp", "anypercent.stamp", S3, checker, stampV(K3, WALLET_A, 6180, H(3))),
  ];
  const runs = [
    raw("run", "anypercent.run", K1, WALLET_A, runV(6170, H(1))),
    raw("run", "anypercent.run", K2, WALLET_A, runV(6050, H(2))),
    raw("run", "anypercent.run", K3, WALLET_B, runV(6180, H(3))),
    raw("run", "anypercent.run", K4, WALLET_A, runV(6200, H(4))),
  ];
  const listings = [raw("listing", "anypercent.listing", L1, WALLET_A, listingV(K1, 6170, H(1))), raw("listing", "anypercent.listing", L2, STRANGER, listingV(K1, 6170, H(1)))];
  return { stamps, runs, listings };
}

// ---- the join (board.ts) ---------------------------------------------------------------------

const asRun = (key: string, creator: string, v: ReturnType<typeof runV>): RunRow => ({
  key,
  creator,
  expiresAt: 1n,
  game: v.game,
  season: v.season,
  frames: BigInt(v.frames),
  log_h: v.log_h,
  runner: v.runner,
  book: v.book,
  human: v.human,
  splits: [v.s1, v.s2, v.s3],
});
const asStamp = (key: string, v: ReturnType<typeof stampV>): StampRow => ({ key, creator: C.toLowerCase(), expiresAt: 1n, run: v.run, console: v.console, game: v.game, season: v.season, frames: BigInt(v.frames), log_h: v.log_h, book: v.book, human: v.human, splits: [v.s1, v.s2, v.s3], tool: v.tool });
const asListing = (key: string, creator: string, v: ReturnType<typeof listingV>): ListingRow => ({ key, creator, expiresAt: 1n, run: v.run, game: v.game, season: v.season, frames: BigInt(v.frames), log_h: v.log_h, price: v.price, seller: v.seller, book: v.book, human: v.human, pay_to: v.pay_to });

describe("the readers' rule: a run counts only when a checker stamp names it and its creator is the stamp's console", () => {
  const stamps = [asStamp(S4, stampV(K4, WALLET_A, 6100, H(4))), asStamp(S1, stampV(K1, WALLET_A, 6170, H(1))), asStamp(S3, stampV(K3, WALLET_A, 6180, H(3)))];
  const runs = [asRun(K1, WALLET_A, runV(6170, H(1))), asRun(K2, WALLET_A, runV(6050, H(2))), asRun(K3, WALLET_B, runV(6180, H(3))), asRun(K4, WALLET_A, runV(6200, H(4)))];
  const listings = [asListing(L1, WALLET_A, listingV(K1, 6170, H(1))), asListing(L2, STRANGER, listingV(K1, 6170, H(1)))];

  it("the five-row mix: K1 and its owner's listing L1 are kept, everything else is dropped", () => {
    const j = joinBoard(stamps, runs, listings);
    assert.deepEqual(j.runs.map((r) => r.key), [K1]);
    assert.deepEqual([j.runs[0].owner, j.runs[0].stamp], [WALLET_A, S1], "each kept run says whose it is and which stamp names it");
    assert.deepEqual(j.listings.map((l) => l.key), [L1]);
    assert.equal(j.dropped, 3);
    assert.ok(j.why.some((w) => w.startsWith(`stamp ${S4}: frames`)), j.why.join("\n"));
    assert.ok(j.why.some((w) => w.startsWith(`stamp ${S3}: created by another wallet`)), j.why.join("\n"));
    assert.ok(j.why.some((w) => w.startsWith(`listing ${L2}: created by another wallet`)), j.why.join("\n"));
  });

  it("any copied column that disagrees drops the run: game, season, log_h, book or label, human, splits", () => {
    const base = stampV(K1, WALLET_A, 6170, H(1));
    for (const [what, over] of [
      ["game", { game: "SHIP" }],
      ["season", { season: 2 }],
      ["log_h", { log_h: H(9) }],
      ["book", { book: "ANY-ZZZ" }],
      ["human", { human: false }],
      ["splits", { s3: 2000 }],
    ] as const) {
      const st = { ...asStamp(S1, { ...base, ...over } as ReturnType<typeof stampV>), ...(what === "splits" ? { splits: [2087, 1995, 2000] } : {}) };
      assert.deepEqual(joinBoard([st], runs, []).runs, [], what);
    }
    const label = { ...asStamp(S1, base), book: undefined, label: "BOT-A1" };
    assert.deepEqual(joinBoard([label], runs, []).runs, [], "label");
  });

  it("a stamp whose run is gone counts for nothing; two stamps of one log count once", () => {
    assert.deepEqual(joinBoard([asStamp(S1, stampV(k(99), WALLET_A, 6170, H(1)))], runs, []).runs, []);
    const twice = joinBoard([asStamp(S1, stampV(K1, WALLET_A, 6170, H(1))), asStamp(k(41), stampV(K1, WALLET_A, 6170, H(1)))], runs, []);
    assert.deepEqual(twice.runs.map((r) => r.stamp), [S1]);
  });

  it("a listing counts only for a stamped run, from its owner, with the run's columns", () => {
    const st = [asStamp(S1, stampV(K1, WALLET_A, 6170, H(1)))];
    assert.deepEqual(joinBoard(st, runs, [asListing(L1, WALLET_A, listingV(K2, 6050, H(2)))]).listings, [], "its run is not stamped");
    assert.deepEqual(joinBoard(st, runs, [asListing(L1, WALLET_A, { ...listingV(K1, 6170, H(1)), frames: 6000 })]).listings, [], "other frames");
    assert.deepEqual(joinBoard(st, runs, [{ ...asListing(L1, WALLET_A, listingV(K1, 6170, H(1))), book: "ANY-ZZZ" }]).listings, [], "another book");
  });
});

// ---- the real port, against a node that honours the pins ----------------------------------------------

type Raw = ReturnType<typeof raw>;

/** A stub of arkiv_query over these rows: schema, $key, run, log_h, game, season and $creator are matched as the node would. */
class Node extends SdkArkiv {
  sent: string[] = [];
  constructor(private readonly rows: Raw[]) {
    super({ rpcUrl: "http://127.0.0.1:9", accessKey: "unused-in-tests", checkerAddress: C });
  }
  override async query(query: string) {
    this.sent.push(query);
    const attr = (r: Raw, n: string) => r.attributes.find((a) => a.name === n)?.value;
    const want = (re: RegExp) => re.exec(query)?.[1];
    const schema = want(/arkiv\.schema = str\('([^']+)'\)/);
    const creator = want(/\$creator = addr\((0x[0-9a-fA-F]{40})\)/);
    const key = want(/\$key = key\((0x[0-9a-f]{64})\)/);
    const run = want(/ run = key\((0x[0-9a-f]{64})\)/);
    const data = this.rows.filter(
      (r) =>
        attr(r, "arkiv.schema") === schema &&
        (!creator || r.creator === creator.toLowerCase()) &&
        (!key || r.key === key) &&
        (!run || String(attr(r, "run")).toLowerCase() === run),
    );
    if (/ORDER BY frames:u64 ASC/.test(query)) data.sort((a, b) => Number(attr(a, "frames")) - Number(attr(b, "frames")));
    return { data, blockNumber: 7n };
  }
}

describe("the real port reads stamps, then each stamped console's runs and listings", () => {
  const mix = rawMix(C);
  const node = () => new Node([...mix.stamps, ...mix.runs, ...mix.listings]);

  it("boardRuns: the stamps pinned to the checker, the runs pinned to each wallet a stamp names; only K1 counts", async () => {
    const n = node();
    const runs = await n.boardRuns("MDGP", 1);
    assert.deepEqual(runs.map((r) => [r.key, r.owner, r.stamp]), [[K1, WALLET_A, S1]]);
    assert.equal(n.sent[0], Q.q1Stamps("MDGP", 1, C));
    assert.deepEqual(n.sent.slice(1), [Q.q1Board("MDGP", 1, WALLET_A)], "one Q1 per stamped console, pinned to it (EIP-55)");
    assert.ok(n.sent[1].includes(`addr(${getAddress(WALLET_A)})`));
  });

  it("boardListings: only the owner's listing of a stamped run", async () => {
    const n = node();
    assert.deepEqual((await n.boardListings("MDGP", 1)).map((l) => l.key), [L1]);
    assert.ok(n.sent.includes(Q.q2Listings("MDGP", 1, WALLET_A)));
  });

  it("getRun: by its stamp, then the run pinned to the stamp's console", async () => {
    const n = node();
    const r = await n.getRun(K1, false);
    assert.deepEqual([r?.key, r?.owner, r?.stamp], [K1, WALLET_A, S1]);
    assert.deepEqual(n.sent, [Q.qStampForRun(K1, C), Q.q6Run(K1, WALLET_A)]);
    assert.equal(await n.getRun(K2, false), null, "no stamp");
    assert.equal(await n.getRun(K3, false), null, "the stamp names another wallet");
    assert.equal(await n.getRun(K4, false), null, "the stamp disagrees");
  });

  it("getListing: whatever its creator on the read, then counted only when it is the stamped run's owner", async () => {
    const n = node();
    assert.equal((await n.getListing(L1))?.key, L1);
    assert.equal(n.sent[0], Q.q6ListingByKey(L1));
    assert.equal(await n.getListing(L2), null, "a stranger's listing of a stamped run");
  });

  it("the snapshot's pages (boardPages) join to the same board", async () => {
    const n = node();
    const pages = await n.boardPages("MDGP", 1);
    assert.deepEqual([pages.stamps.length, pages.runs.length, pages.listings.length], [3, 3, 1], "WALLET_A's own rows only");
    assert.deepEqual(n.joinPages(pages).runs.map((r) => r.key), [K1]);
  });
});

// ---- the web board: the same rule in the page's own JS --------------------------------------------------

function page() {
  const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
  const js = html.split("<script>")[1].split("</script>")[0].split("// ---- State")[0];
  return runInNewContext(`${js}\n;({ boardFrom, joinBoard, eip55, keccak256, Q, CHECKER, STAMP_ATTRS })`, { BigInt, Number, TextEncoder, document: {}, location: {} }) as {
    boardFrom: (s: unknown[], r: unknown[], l: unknown[]) => { runs: Array<Record<string, unknown>>; listings: Array<Record<string, unknown>>; dropped: number; unstamped: number };
    eip55: (a: string) => string;
    keccak256: (b: Uint8Array) => Uint8Array;
    Q: Record<string, (...a: unknown[]) => string>;
    CHECKER: string;
    STAMP_ATTRS: string[];
  };
}

describe("the web board mirrors the rule (public/board.html, no build step)", () => {
  it("the five-row mix gives what the bridge gives: K1 (its owner and stamp) and L1", () => {
    const p = page();
    const mix = rawMix(p.CHECKER);
    const out = JSON.parse(JSON.stringify(p.boardFrom(mix.stamps, mix.runs, mix.listings))) as ReturnType<typeof p.boardFrom>; // (another realm: compare plain copies)
    assert.deepEqual(out.runs.map((r) => [r.key, r.owner, r.stamp]), [[K1, WALLET_A, S1]]);
    assert.deepEqual(out.listings.map((l) => l.key), [L1]);
    assert.equal(out.unstamped, 3);
    const bridge = new Node([]).joinPages({ block: 1n, stamps: rawMix(C).stamps, runs: mix.runs, listings: mix.listings });
    assert.deepEqual(out.runs.map((r) => r.key), bridge.runs.map((r) => r.key));
  });

  it("a stamp not created by the checker is not a stamp", () => {
    const p = page();
    const mix = rawMix(STRANGER);
    assert.equal(p.boardFrom(mix.stamps, mix.runs, mix.listings).runs.length, 0);
  });

  it("writes each console wallet EIP-55 in a query (keccak-256 in the page, checked against viem)", () => {
    const p = page();
    assert.equal(Buffer.from(p.keccak256(new Uint8Array())).toString("hex"), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470");
    assert.equal(Buffer.from(p.keccak256(new TextEncoder().encode("abc"))).toString("hex"), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45");
    const long = new Uint8Array(300).map((_, i) => (i * 31) & 0xff);
    assert.equal(`0x${Buffer.from(p.keccak256(long)).toString("hex")}`, viemKeccak(long), "past one 136-byte block");
    assert.equal(`0x${Buffer.from(p.keccak256(toBytes("x".repeat(136)))).toString("hex")}`, viemKeccak(toBytes("x".repeat(136))), "exactly one block");
    for (const a of [WALLET_A, WALLET_B, STRANGER, "0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed", "0xfb6916095ca1df60bb79ce92ce3ea74c37c5d359", C.toLowerCase()]) assert.equal(p.eip55(a), getAddress(a), a);
  });

  it("sends the stamp query and the per-console run and listing queries in the bridge's own words", () => {
    const p = page();
    assert.equal(p.Q.stamps("MDGP", 1, C), Q.q1Stamps("MDGP", 1, C));
    assert.equal(p.Q.q1("MDGP", 1, getAddress(WALLET_A)), Q.q1Board("MDGP", 1, WALLET_A));
    assert.equal(p.Q.q2("MDGP", 1, getAddress(WALLET_A)), Q.q2Listings("MDGP", 1, WALLET_A));
    assert.deepEqual(JSON.parse(JSON.stringify(p.STAMP_ATTRS)), [...Q.STAMP_ATTRS]);
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    assert.ok(html.includes(Q.Q1_STAMPS_TEMPLATE), "board.html must contain the stamp query exactly");
    assert.ok(!/OPEN/.test(html), "no OPEN badge: every row is a console's or the house's, stamped");
    assert.ok(!/ACCESS_KEY|accessKey/.test(html), "the page sends no key");
  });
});

describe("npm run arkiv:fund: tGLM from the checker to a console's wallet", () => {
  it("takes a wallet and an amount, checked before anything is signed", async () => {
    const { fundPlan, MAX_FUND_GLM } = await import("../scripts/arkiv-fund.js");
    const ok = fundPlan(WALLET_A, "1", C);
    assert.deepEqual(ok, { to: getAddress(WALLET_A), wei: 10n ** 18n });
    assert.deepEqual(fundPlan(WALLET_A, "0.25", C), { to: getAddress(WALLET_A), wei: 25n * 10n ** 16n });
    for (const [to, amount] of [
      [undefined, "1"],
      ["0x12", "1"],
      [`0x${"0".repeat(40)}`, "1"],
      [C, "1"],
      [WALLET_A, undefined],
      [WALLET_A, "-1"],
      [WALLET_A, "0"],
      [WALLET_A, "1e3"],
      [WALLET_A, String(MAX_FUND_GLM + 1)],
    ] as const) {
      assert.ok("error" in fundPlan(to, amount, C), `${to} ${amount}`);
    }
  });
});
