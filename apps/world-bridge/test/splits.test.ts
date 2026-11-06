/**
 * Splits on Arkiv: what publish writes (s1..sN, split_kind) and when it writes none, the readers'
 * rules (old rows still load, splits that do not add up are dropped), label listings, Q10, and the
 * real splits tool's output read through the WSL runner (a fake exec).
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { createPublicClient } from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { and, asc, eq } from "@arkiv-network/sdk/query";
import { i32, str } from "@arkiv-network/sdk/schema";
import { custom } from "viem";
import { RealChecker, splitsVerdict } from "../src/arkiv/checker.js";
import { actionText, Publisher, type PublishView } from "../src/arkiv/publish.js";
import * as Q from "../src/arkiv/queries.js";
import { decodeRow, splitsOf } from "../src/arkiv/rows.js";
import { LISTING_TYPES, Run, RUN_TYPES } from "../src/arkiv/schema.js";
import { defaultSplitsTool, explorerLinks, loadConfig, splitsReady } from "../src/config.js";
import { nullifierKey } from "../src/hmac.js";
import { Store } from "../src/store.js";
import { consoleFinish, FakeArkiv, FakeChecker, linkWallet, makeLog, WALLET_A } from "./fake-arkiv.js";
import { FakeSplits } from "./fake-splits.js";
import { SECRET, tempDir, waitFor } from "./helpers.js";

const GHOST = "ab".repeat(32);
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const C = "0x8ba1f109551bD432803012645Ac136ddd64DBA72";
const K = `0x${"12ab".repeat(16)}`;

let n = 0;
function setup(splits: FakeSplits | null = new FakeSplits(), frames = 6170) {
  n += 1;
  const store = new Store(tempDir(), SECRET);
  const rec = store.claimBook(nullifierKey(SECRET, "act", `split-${n}`), "Orb", "0123456789abcdef", 1, "session_x").record;
  const arkiv = new FakeArkiv();
  const checker = new FakeChecker(frames);
  const lines: string[] = [];
  const pub = new Publisher({
    arkiv,
    checker,
    splits,
    explorer: explorerLinks(loadConfig({}, ".").explorer),
    store,
    season: 1,
    runExpiry: new Date(Date.now() + 60 * 86_400_000),
    priceC: 10,
    ghostSecret: GHOST,
    chainId: 7794095,
    rpc: "https://rpc.example",
    verifyGapMs: 1,
    log: (l) => lines.push(l),
  });
  linkWallet(store, rec.book, WALLET_A);
  const action = actionText("MARINE DRIVE GP", frames, 10);
  store.recordApproval("jti-split", rec.book, sha(action), Math.floor(Date.now() / 1000));
  const log = makeLog("MDGP", 4, frames);
  const body = { book: rec.book, jti: "jti-split", action, game: "MDGP", title: "MARINE DRIVE GP", frames, price_c: 10, log: Buffer.from(log).toString("base64") };
  return { store, arkiv, checker, splits, lines, pub, body };
}

/** The listing through the console (its linked wallet signs what was issued) to the stamp. */
async function publish(s: ReturnType<typeof setup>): Promise<PublishView> {
  return consoleFinish(s.pub, s.arkiv, s.pub.start(s.body).id);
}

describe("publish issues lap splits on the run (and the stamp copies them)", () => {
  it("the happy path: s1..s3 and split_kind, from arcade_splits, and explorer links in the done view", async () => {
    const s = setup();
    const v = await publish(s);
    assert.equal(v.ok, true, JSON.stringify(v));
    const rv = s.arkiv.runs[0].spec.values;
    assert.deepEqual([rv.s1, rv.s2, rv.s3, rv.s4, rv.split_kind], [2087, 1995, 2088, undefined, "lap"]);
    assert.equal(s.splits!.calls, 1);
    assert.deepEqual(v.data.explorer, {
      tx: `https://rabdi.explorer.arkiv.network/tx/${v.data.tx}`,
      run: `https://rabdi.explorer.arkiv.network/entity/${v.data.run}`,
      listing: `https://rabdi.explorer.arkiv.network/entity/${v.data.listing}`,
      stamp: `https://rabdi.explorer.arkiv.network/entity/${v.data.stamp}`,
      stamp_tx: `https://rabdi.explorer.arkiv.network/tx/${v.data.stamp_tx}`,
    });
  });

  const noSplits = async (s: ReturnType<typeof setup>, why: RegExp) => {
    const v = await publish(s);
    assert.equal(v.ok, true, "splits never fail a publish");
    const rv = s.arkiv.runs[0].spec.values;
    assert.deepEqual([rv.s1, rv.s2, rv.s3, rv.split_kind], [undefined, undefined, undefined, undefined]);
    assert.ok(s.lines.some((l) => /splits not written/.test(l) && why.test(l)), s.lines.join("\n"));
  };

  it("a sum that is not the replayed time: no splits, published", async () => {
    const s = setup(new FakeSplits([2087, 1995, 2000]));
    await noSplits(s, /add up to 6082, not 6170/);
  });
  it("another replay (final hash differs): no splits, published", async () => {
    const sp = new FakeSplits();
    sp.finalHash = 1;
    await noSplits(setup(sp), /final hash/);
  });
  it("the tool missing: no splits, published", async () => {
    const sp = new FakeSplits();
    sp.missing = true;
    await noSplits(setup(sp), /splits tool: exit 127/);
  });
  it("a game not in SPLIT_GAMES is never asked", async () => {
    const s = setup(new FakeSplits([2087, 1995, 2088], ["RUSH"]));
    const v = await publish(s);
    assert.equal(v.ok, true);
    assert.equal(s.splits!.calls, 0);
    assert.equal(s.arkiv.runs[0].spec.values.s1, undefined);
  });
  it("no splits port at all (an older config): published as before", async () => {
    const s = setup(null);
    const v = await publish(s);
    assert.equal(v.ok, true);
    assert.equal(s.arkiv.runs[0].spec.values.split_kind, undefined);
  });
});

describe("splitsVerdict", () => {
  const ok = { kind: "lap", splits: [2087, 1995, 1994], time_frames: 6076, finished: true, final_hash: 7 };
  it("laps that add up, from the same replay", () => assert.deepEqual(splitsVerdict(ok, 6076, 7), { ok: true, splits: [2087, 1995, 1994] }));
  it("refuses another kind, a zero, five splits, a sum mismatch, another hash", () => {
    assert.equal(splitsVerdict({ ...ok, kind: "section" }, 6076, 7).ok, false);
    assert.equal(splitsVerdict({ ...ok, splits: [6076, 0] }, 6076, 7).ok, false);
    assert.equal(splitsVerdict({ ...ok, splits: [1, 1, 1, 1, 6072] }, 6076, 7).ok, false);
    assert.equal(splitsVerdict(ok, 6077, 7).ok, false);
    assert.equal(splitsVerdict(ok, 6076, 8).ok, false);
    assert.equal(splitsVerdict(ok, 6076, undefined).ok, false);
  });
});

describe("readers: old rows load, splits that do not check out are absent", () => {
  const run = (extra: Array<{ name: string; type: string; value: unknown }>) => ({
    key: K,
    creator: C.toLowerCase(),
    attributes: [
      { name: "arkiv.schema", type: "str", value: "anypercent.run" },
      { name: "game", type: "str", value: "MDGP" },
      { name: "title", type: "str", value: "MARINE DRIVE GP" },
      { name: "frames", type: "u64", value: "0x17bc" }, // 6076
      { name: "runner", type: "str", value: "0123456789abcdef" },
      { name: "human", type: "bool", value: false },
      { name: "label", type: "str", value: "BOT-A1" },
      { name: "log_h", type: "str", value: "f".repeat(64) },
      { name: "rules", type: "u64", value: "0x4" },
      ...extra,
    ],
  });
  const lap = (k: number, v: number) => ({ name: `s${k}`, type: "u64", value: `0x${v.toString(16)}` });
  const kind = { name: "split_kind", type: "str", value: "lap" };
  const read = (extra: Array<{ name: string; type: string; value: unknown }>) => {
    const r = decodeRow(run(extra), RUN_TYPES, Q.RUN_BOARD_ATTRS, "anypercent.run", C);
    assert.ok("row" in r, "the row is kept");
    return splitsOf(r.row.values);
  };
  it("a row without splits (every row before this build) loads, with none", () => assert.equal(read([]), null));
  it("laps that add up are read", () => assert.deepEqual(read([lap(1, 2087), lap(2, 1995), lap(3, 1994), kind]), [2087, 1995, 1994]));
  it("not contiguous, another kind, a zero, or a sum other than frames: absent, row kept", () => {
    assert.equal(read([lap(1, 2087), lap(3, 3989), kind]), null);
    assert.equal(read([lap(1, 2087), lap(2, 1995), lap(3, 1994), { ...kind, value: "section" }]), null);
    assert.equal(read([lap(1, 2087), lap(2, 1995), lap(3, 1994)]), null);
    assert.equal(read([lap(1, 0), lap(2, 4082), lap(3, 1994), kind]), null);
    assert.equal(read([lap(1, 2087), lap(2, 1995), lap(3, 1995), kind]), null);
  });

  const listing = (extra: Array<{ name: string; type: string; value: unknown }>) => ({
    key: K,
    creator: C.toLowerCase(),
    attributes: [
      { name: "arkiv.schema", type: "str", value: "anypercent.listing" },
      { name: "run", type: "bytes32", value: K },
      { name: "game", type: "str", value: "MDGP" },
      { name: "season", type: "i32", value: 1 },
      { name: "frames", type: "u64", value: "0x17bc" },
      { name: "log_h", type: "str", value: "f".repeat(64) },
      { name: "price", type: "dec", value: "0.1" },
      { name: "seller", type: "str", value: "0123456789abcdef" },
      { name: "human", type: "bool", value: false },
      { name: "pay_to", type: "str", value: "0.0.4004004" },
      ...extra,
    ],
  });
  it("a label-only listing decodes; one with both or neither of book and label is dropped", () => {
    const l = decodeRow(listing([{ name: "label", type: "str", value: "BOT-A1" }]), LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C);
    assert.ok("row" in l && l.row.values.label === "BOT-A1" && l.row.values.book === undefined);
    const both = decodeRow(listing([{ name: "label", type: "str", value: "BOT-A1" }, { name: "book", type: "str", value: "ANY-6PS" }]), LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C);
    assert.ok("dropped" in both);
    const neither = decodeRow(listing([]), LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C);
    assert.ok("dropped" in neither);
    const book = decodeRow(listing([{ name: "book", type: "str", value: "ANY-6PS" }]), LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C);
    assert.ok("row" in book, "a person's listing still decodes");
  });
});

describe("Q10: the lap leaders, one indexed column in one query", () => {
  it("is the exact string the SDK's builder renders", () => {
    const client = createPublicClient({ chain: rabdi({ accessKey: "unused-in-tests" }), transport: custom({ request: async () => { throw new Error("no network"); } }) });
    const built = client.select({ $key: true }).from(Run).where(and(eq("game", str("MDGP")), eq("season", i32(1)))).createdBy(C).orderBy(asc("s2")).toString();
    assert.equal(Q.q10LapLeaders("MDGP", 1, C), built);
    assert.equal(
      Q.q10LapLeaders("MDGP", 1, C),
      `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) AND $creator = addr(${C}) ORDER BY s2:u64 ASC`,
    );
    assert.ok(Q.q10LapLeaders("MDGP", 1, C, 3).endsWith("ORDER BY s3:u64 ASC"));
    assert.throws(() => Q.q10LapLeaders("MDGP", 1, C, 5));
  });
  it("Q1-Q9 keep their exact text; the board selects the split columns and listings select label", () => {
    assert.ok(Q.q1Board("MDGP", 1, C).endsWith("ORDER BY frames:u64 ASC"));
    for (const c of ["s1", "s2", "s3", "s4", "split_kind"]) assert.ok((Q.RUN_BOARD_ATTRS as readonly string[]).includes(c));
    assert.ok((Q.LISTING_ATTRS as readonly string[]).includes("label"));
  });
});

describe("the real splits tool, through the runner", () => {
  it("reads arcade_splits' JSON line, through wsl.exe with the /mnt/c path", async () => {
    const calls: string[][] = [];
    const checker = new RealChecker({
      replay: "/opt/arca-sandbox/games/arcade/{game}/arcade_replay",
      splits: "/opt/arca-sandbox/games/arcade/{game}/arcade_splits",
      splitGames: ["MDGP"],
      wsl: "Ubuntu-24.04",
      dir: "C:\\bridge\\data\\checker",
      exec: async (cmd, args) => {
        calls.push([cmd, ...args]);
        return '{"game":"MDGP","kind":"lap","splits":[2087,1995,1994],"time_frames":6076,"finished":true,"final_hash":576543229}\n';
      },
    });
    const h = "a".repeat(64);
    // Writing the log goes to a temp dir in the test, not C:\bridge.
    (checker as unknown as { opts: { dir: string } }).opts.dir = tempDir();
    const r = await checker.splits("MDGP", h, makeLog());
    assert.deepEqual(r, { game: "MDGP", kind: "lap", splits: [2087, 1995, 1994], time_frames: 6076, finished: true, final_hash: 576543229 });
    assert.deepEqual(calls[0].slice(0, 5), ["wsl.exe", "-d", "Ubuntu-24.04", "-e", "/opt/arca-sandbox/games/arcade/MDGP/arcade_splits"]);
    await assert.rejects(checker.splits("RUSH", h, makeLog("RUSH")), /no splits for RUSH/);
    assert.deepEqual(checker.games, ["MDGP"]);
  });
  it("CHECKER_SPLITS defaults to arcade_splits beside CHECKER_REPLAY; /health splits follows it", () => {
    assert.equal(defaultSplitsTool("/opt/arca-sandbox/games/arcade/{game}/arcade_replay"), "/opt/arca-sandbox/games/arcade/{game}/arcade_splits");
    assert.equal(defaultSplitsTool(""), "");
    assert.equal(splitsReady(loadConfig({ CHECKER_REPLAY: "/x/{game}/arcade_replay" }, ".")), true);
    assert.equal(splitsReady(loadConfig({}, ".")), false);
    assert.deepEqual(loadConfig({ SPLIT_GAMES: "mdgp, RUSH,bad!" }, ".").splits.games, ["MDGP", "RUSH"]);
  });
});

describe("the web board reads splits, label listings and Q10 in the same words", () => {
  const html = () => readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "public", "board.html"), "utf8");
  it("carries Q10's template (on the stamps, which copy the splits) and selects the split columns and label", () => {
    const h = html();
    const tpl = Q.q10LapStamps("MDGP", 1, C, 2).replace("'MDGP'", "'${game}'").replace("i32(1)", "i32(${season})").replace(`addr(${C})`, "addr(${checker})").replace("s2:u64", "s${lap}:u64");
    assert.ok(h.includes(tpl), `board.html misses ${tpl}`);
    for (const c of ['"s1"', '"s2"', '"s3"', '"s4"', '"split_kind"', '"label"']) assert.ok(h.includes(c), c);
    assert.ok(h.includes("generated by a program (dev/ghostgen.py), written by the house wallet, sold by the house account"));
    assert.ok(h.includes("Humans on this board: "));
  });
  it("decodes a label-only listing, drops both or neither, and reads laps like the service", async () => {
    const { runInNewContext } = await import("node:vm");
    const js = html().split("<script>")[1].split("</script>")[0].split("// ---- State")[0];
    const page = runInNewContext(`${js}\n;({ decodeAll, splitsOf, isBot, LISTING_TYPES, LISTING_REQUIRED, CHECKER })`, { BigInt, Number, document: {}, location: {} }) as {
      decodeAll: (d: unknown[], t: unknown, r: unknown, s: string, pin: string) => { rows: Array<Record<string, unknown>>; dropped: number };
      splitsOf: (r: Record<string, unknown>) => number[] | null;
      isBot: (r: Record<string, unknown>) => boolean;
      LISTING_TYPES: unknown;
      LISTING_REQUIRED: unknown;
      CHECKER: string;
    };
    const base = (extra: Array<{ name: string; type: string; value: unknown }>) => ({
      key: K,
      creator: page.CHECKER.toLowerCase(),
      attributes: [
        { name: "arkiv.schema", type: "str", value: "anypercent.listing" },
        { name: "run", type: "bytes32", value: K },
        { name: "game", type: "str", value: "MDGP" },
        { name: "season", type: "i32", value: 1 },
        { name: "frames", type: "u64", value: "0x185c" },
        { name: "log_h", type: "str", value: "f".repeat(64) },
        { name: "price", type: "dec", value: "0.1" },
        { name: "seller", type: "str", value: "0123456789abcdef" },
        { name: "human", type: "bool", value: false },
        ...extra,
      ],
    });
    const out = page.decodeAll(
      [base([{ name: "label", type: "str", value: "BOT-A2" }]), base([]), base([{ name: "label", type: "str", value: "BOT-A2" }, { name: "book", type: "str", value: "ANY-6PS" }])],
      page.LISTING_TYPES,
      page.LISTING_REQUIRED,
      "anypercent.listing",
      page.CHECKER,
    );
    assert.equal(out.rows.length, 1);
    assert.equal(out.rows[0].label, "BOT-A2");
    assert.equal(out.dropped, 2);
    assert.deepEqual([...(page.splitsOf({ frames: 6236, s1: 2248, s2: 1994, s3: 1994, split_kind: "lap" }) ?? [])], [2248, 1994, 1994], "(another realm: compare its items)");
    assert.equal(page.splitsOf({ frames: 6236, s1: 2248, s3: 3988, split_kind: "lap" }), null);
    assert.equal(page.splitsOf({ frames: 6237, s1: 2248, s2: 1994, s3: 1994, split_kind: "lap" }), null);
    assert.equal(page.splitsOf({ frames: 6236 }), null);
    assert.equal(page.isBot({ label: "BOT-A2", human: false }), true);
    assert.equal(page.isBot({ label: "BOT-A2", human: true }), false, "never HUMAN");
  });
});
