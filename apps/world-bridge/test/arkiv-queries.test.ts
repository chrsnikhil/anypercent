/** Q1-Q9 are exact strings, the same ones the SDK's builder renders, and the web board carries Q1. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { createPublicClient } from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { and, asc, desc, eq, lt } from "@arkiv-network/sdk/query";
import { addr, bool, i32, key, str, u64 } from "@arkiv-network/sdk/schema";
import { custom } from "viem";
import * as Q from "../src/arkiv/queries.js";
import { decodePage, decodeRow } from "../src/arkiv/rows.js";
import { Listing, LISTING_TYPES, Run, RUN_TYPES, SMOKE } from "../src/arkiv/schema.js";

const C = "0x8ba1f109551bD432803012645Ac136ddd64DBA72"; // EIP-55
const C_LOWER = C.toLowerCase();
const K = `0x${"12ab".repeat(16)}`;
const H = "f".repeat(64);
const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("the query strings, exactly", () => {
  it("Q1", () => {
    assert.equal(
      Q.q1Board("MDGP", 1, C),
      `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) AND $creator = addr(${C}) ORDER BY frames:u64 ASC`,
    );
    assert.equal(Q.q1Board("MDGP", 1, C_LOWER), Q.q1Board("MDGP", 1, C), "the checker is always written EIP-55");
    assert.equal(Q.Q1_TEMPLATE.replace("${game}", "MDGP").replace("${season}", "1").replace("${creator}", C), Q.q1Board("MDGP", 1, C));
    assert.equal(Q.Q1_STAMPS_TEMPLATE.replace("${game}", "MDGP").replace("${season}", "1").replace("${checker}", C), Q.q1Stamps("MDGP", 1, C));
  });
  it("Q2", () => {
    assert.equal(
      Q.q2Listings("MDGP", 1, C),
      `arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(1) AND $creator = addr(${C}) ORDER BY frames:u64 ASC`,
    );
  });
  it("Q3: the listed ghost just ahead of 1:44.83", () => {
    assert.equal(
      Q.q3JustAhead("MDGP", 1, 6290, C),
      `arkiv.schema = str('anypercent.listing') AND game = str('MDGP') AND season = i32(1) AND frames < u64(6290) AND $creator = addr(${C}) ORDER BY frames:u64 DESC`,
    );
  });
  it("Q4 (by book and by runner) and Q5", () => {
    assert.equal(Q.q4BookRuns("ANY-6PS", C), `arkiv.schema = str('anypercent.run') AND book = str('ANY-6PS') AND $creator = addr(${C}) ORDER BY frames:u64 ASC`);
    assert.equal(Q.q4RunnerRuns("0123456789abcdef", C), `arkiv.schema = str('anypercent.run') AND runner = str('0123456789abcdef') AND $creator = addr(${C}) ORDER BY frames:u64 ASC`);
    assert.equal(Q.q5BookListings("ANY-6PS", C), `arkiv.schema = str('anypercent.listing') AND book = str('ANY-6PS') AND $creator = addr(${C}) ORDER BY $expiresAt:u64 ASC`);
  });
  it("Q6 on listings and runs; Q7", () => {
    assert.equal(Q.q6Listing(K, C), `arkiv.schema = str('anypercent.listing') AND $key = key(${K}) AND $creator = addr(${C})`);
    assert.equal(Q.q6Run(K.toUpperCase().replace("0X", "0x"), C), `arkiv.schema = str('anypercent.run') AND $key = key(${K}) AND $creator = addr(${C})`);
    assert.equal(Q.q7RunByLogHash(H, C), `arkiv.schema = str('anypercent.run') AND log_h = str('${H}') AND $creator = addr(${C})`);
  });
  it("the stamp reads: the board, one run's stamp, one book's stamps, the lap leaders; a listing by key with no pin", () => {
    assert.equal(Q.q1Stamps("MDGP", 1, C), `arkiv.schema = str('anypercent.stamp') AND game = str('MDGP') AND season = i32(1) AND $creator = addr(${C}) ORDER BY frames:u64 ASC`);
    assert.equal(Q.qStampForRun(K, C), `arkiv.schema = str('anypercent.stamp') AND run = key(${K}) AND $creator = addr(${C})`);
    assert.equal(Q.q4BookStamps("ANY-6PS", C), `arkiv.schema = str('anypercent.stamp') AND book = str('ANY-6PS') AND $creator = addr(${C}) ORDER BY frames:u64 ASC`);
    assert.equal(Q.q10LapStamps("MDGP", 1, C, 3), `arkiv.schema = str('anypercent.stamp') AND game = str('MDGP') AND season = i32(1) AND $creator = addr(${C}) ORDER BY s3:u64 ASC`);
    assert.equal(Q.q6ListingByKey(K), `arkiv.schema = str('anypercent.listing') AND $key = key(${K})`);
    assert.throws(() => Q.qStampForRun("0x12", C));
    assert.throws(() => Q.q4BookStamps("ANY-6PS') OR true", C));
  });
  it("Q8 (no pin) and Q9 (HUMAN only)", () => {
    assert.equal(Q.q8AnyWallet("MDGP", 1), "arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) ORDER BY frames:u64 ASC");
    assert.equal(
      Q.q9Human("MDGP", 1, C),
      `arkiv.schema = str('anypercent.run') AND game = str('MDGP') AND season = i32(1) AND human = true AND $creator = addr(${C}) ORDER BY frames:u64 ASC`,
    );
  });
  it("the smoke twins differ only in the schema name", () => {
    assert.equal(Q.q1Board("MDGP", 1, C, SMOKE), Q.q1Board("MDGP", 1, C).replace("'anypercent.run'", "'anypercent.smoke.run'"));
  });
  it("refuses inputs that could widen a query", () => {
    assert.throws(() => Q.q1Board("MDGP') OR game = str('x", 1, C));
    assert.throws(() => Q.q4BookRuns("ANY-6PS') OR true", C));
    assert.throws(() => Q.q1Board("MDGP", 1.5, C));
    assert.throws(() => Q.q6Run("0x12", C));
    assert.throws(() => Q.q1Board("MDGP", 1, "0x12"));
    assert.throws(() => Q.q7RunByLogHash("F".repeat(64), C));
  });
  it("a request: limit 0x64 (100), key, creator, expiresAt and the arkiv.schema tag selected", () => {
    const [query, opts] = Q.queryParams(Q.q1Board("MDGP", 1, C), Q.selectOf(Q.RUN_BOARD_ATTRS));
    assert.equal(query, Q.q1Board("MDGP", 1, C));
    assert.equal(opts.limit, "0x64");
    assert.equal(opts.select.key && opts.select.creator && opts.select.expiresAt, true);
    assert.deepEqual(Object.keys(opts.select.attributes!).sort(), ["arkiv.schema", ...Q.RUN_BOARD_ATTRS].sort());
    assert.ok(!("log" in opts.select.attributes!) && !("log_enc" in opts.select.attributes!), "a board never selects ghost bytes");
  });
});

describe("the strings are what SDK 1.0.1's own builder renders", () => {
  const client = createPublicClient({
    chain: rabdi({ accessKey: "unused-in-tests" }),
    transport: custom({ request: async () => { throw new Error("no network in tests"); } }),
  });
  const sel = () => client.select({ $key: true });

  it("the stamp queries through the Stamp schema", async () => {
    const { Stamp } = await import("../src/arkiv/schema.js");
    assert.equal(sel().from(Stamp).where(and(eq("game", str("MDGP")), eq("season", i32(1)))).createdBy(C).orderBy(asc("frames")).toString(), Q.q1Stamps("MDGP", 1, C));
    assert.equal(sel().from(Stamp).where(eq("run", key(K as `0x${string}`))).createdBy(C).toString(), Q.qStampForRun(K, C));
    assert.equal(sel().from(Stamp).where(eq("book", str("ANY-6PS"))).createdBy(C).orderBy(asc("frames")).toString(), Q.q4BookStamps("ANY-6PS", C));
    assert.equal(sel().from(Stamp).where(and(eq("game", str("MDGP")), eq("season", i32(1)))).createdBy(C).orderBy(asc("s2")).toString(), Q.q10LapStamps("MDGP", 1, C, 2));
  });

  it("Q1, Q2, Q3, Q9 through the schemas", () => {
    assert.equal(sel().from(Run).where(and(eq("game", str("MDGP")), eq("season", i32(1)))).createdBy(C).orderBy(asc("frames")).toString(), Q.q1Board("MDGP", 1, C));
    assert.equal(sel().from(Listing).where(and(eq("game", str("MDGP")), eq("season", i32(1)))).createdBy(C).orderBy(asc("frames")).toString(), Q.q2Listings("MDGP", 1, C));
    assert.equal(
      sel().from(Listing).where(and(eq("game", str("MDGP")), eq("season", i32(1)), lt("frames", u64(6290n)))).createdBy(C).orderBy(desc("frames")).toString(),
      Q.q3JustAhead("MDGP", 1, 6290, C),
    );
    assert.equal(
      sel().from(Run).where(and(eq("game", str("MDGP")), eq("season", i32(1)), eq("human", bool(true)))).createdBy(C).orderBy(asc("frames")).toString(),
      Q.q9Human("MDGP", 1, C),
    );
  });

  it("Q4, Q5, Q6, Q7, Q8", () => {
    assert.equal(sel().from(Run).where(eq("book", str("ANY-6PS"))).createdBy(C).orderBy(asc("frames")).toString(), Q.q4BookRuns("ANY-6PS", C));
    assert.equal(sel().from(Listing).where(eq("book", str("ANY-6PS"))).createdBy(C).orderBy(asc("$expiresAt")).toString(), Q.q5BookListings("ANY-6PS", C));
    assert.equal(sel().from(Listing).where(eq("$key", key(K as `0x${string}`))).createdBy(C).toString(), Q.q6Listing(K, C));
    assert.equal(sel().from(Run).where(eq("$key", key(K as `0x${string}`))).createdBy(C).toString(), Q.q6Run(K, C));
    assert.equal(sel().from(Run).where(eq("log_h", str(H))).createdBy(C).toString(), Q.q7RunByLogHash(H, C));
    assert.equal(sel().from(Run).where(and(eq("game", str("MDGP")), eq("season", i32(1)))).orderBy(asc("frames")).toString(), Q.q8AnyWallet("MDGP", 1));
    assert.equal(sel().from(Listing).where(eq("run", key(K as `0x${string}`))).createdBy(C).toString(), Q.qListingForRun(K, C));
    assert.equal(sel().from(Listing).where(eq("$key", key(K as `0x${string}`))).toString(), Q.q6ListingByKey(K));
    assert.equal(addr(C_LOWER).value, C);
  });
});

describe("the web board", () => {
  it("public/board.html carries Q1's exact template and the stamp query's", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    assert.ok(html.includes(Q.Q1_TEMPLATE), "board.html must contain Q1 exactly");
    assert.ok(html.includes(Q.Q1_STAMPS_TEMPLATE), "board.html must contain the stamp query exactly");
  });
  it("and every other query it runs, in the same words (stamps pinned to the checker, rows to the stamp's console)", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    const tpl = (s: string, pin: string) =>
      s.replace("'MDGP'", "'${game}'").replace("i32(1)", "i32(${season})").replace(`addr(${C})`, "addr(${" + pin + "})").replace("'ANY-6PS'", "'${book}'");
    for (const q of [Q.q2Listings("MDGP", 1, C), Q.q4BookRuns("ANY-6PS", C), Q.q5BookListings("ANY-6PS", C)]) assert.ok(html.includes(tpl(q, "creator")), `board.html misses ${tpl(q, "creator")}`);
    assert.ok(html.includes(tpl(Q.q4BookStamps("ANY-6PS", C), "checker")));
    assert.ok(html.includes(tpl(Q.q8AnyWallet("MDGP", 1), "checker")));
  });
  it("is one file: no external script, stylesheet or font", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    assert.ok(!/<script[^>]+src=/i.test(html));
    assert.ok(!/<link[^>]+rel=["']?stylesheet/i.test(html));
    assert.ok(!/@import|fonts\.googleapis/i.test(html));
  });
});

describe("raw rows: decoded and validated like every reader must", () => {
  const good = {
    key: K,
    creator: C_LOWER,
    expiresAt: "0x1000",
    attributes: [
      { name: "arkiv.schema", type: "str", value: "anypercent.run" },
      { name: "game", type: "str", value: "MDGP" },
      { name: "title", type: "str", value: "MARINE DRIVE GP" },
      { name: "frames", type: "u64", value: "0x181a" },
      { name: "runner", type: "str", value: "0123456789abcdef" },
      { name: "book", type: "str", value: "ANY-6PS" },
      { name: "human", type: "bool", value: true },
      { name: "credential", type: "str", value: "Orb" },
      { name: "log_h", type: "str", value: H },
      { name: "rules", type: "u64", value: "0x4" },
    ],
  };
  const asked = Q.RUN_BOARD_ATTRS;

  it("decodes each JSON encoding", () => {
    const r = decodeRow(good, RUN_TYPES, asked, "anypercent.run", C);
    assert.ok("row" in r);
    assert.equal(r.row.values.frames, 6170n);
    assert.equal(r.row.values.human, true);
    assert.equal(r.row.expiresAt, 4096n);
    const l = decodeRow(
      { key: K, creator: C_LOWER, attributes: [{ name: "run", type: "key", value: K }, { name: "season", type: "i32", value: 1 }, { name: "price", type: "dec", value: "0.1" }] },
      LISTING_TYPES,
      ["run", "season", "price"],
      "anypercent.listing",
      C,
    );
    assert.ok("row" in l && l.row.values.season === 1 && l.row.values.price === "0.1" && l.row.values.run === K);
  });

  // A listing exactly as Rabdi answered arkiv_query for a row the SDK wrote with run: key(...).
  const LIVE_LISTING = {
    key: "0x6ed1a7e2d54a55003ea7b93ec8ee95ddec6a07ce07845d1da9b9783e68df1f77",
    creator: C_LOWER,
    expiresAt: "0x41ad0",
    attributes: [
      { name: "arkiv.schema", type: "str", value: "anypercent.listing" },
      { name: "book", type: "str", value: "ANY-SMK" },
      { name: "frames", type: "u64", value: "0x181a" },
      { name: "game", type: "str", value: "MDGP" },
      { name: "human", type: "bool", value: true },
      { name: "log_h", type: "str", value: H },
      { name: "price", type: "dec", value: "0.1" },
      { name: "run", type: "bytes32", value: "0x1A7D31FD898939ADB76280FDAFF8CC5F830C82EF6FD0A00105D4B0D45834CF1D" },
      { name: "season", type: "i32", value: 1 },
      { name: "seller", type: "str", value: "5a5a5a5a5a5a5a5a" },
    ],
  };

  it("a key column comes back tagged bytes32 (as the node answers): read as a key, as the SDK does", () => {
    const r = decodeRow(LIVE_LISTING, LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C);
    assert.ok("row" in r, "dropped" in r ? r.dropped : "");
    assert.equal(r.row.values.run, "0x1a7d31fd898939adb76280fdaff8cc5f830c82ef6fd0a00105d4b0d45834cf1d");
    const tagged = { ...LIVE_LISTING, attributes: LIVE_LISTING.attributes.map((a) => (a.name === "run" ? { ...a, type: "key" } : a)) };
    assert.ok("row" in decodeRow(tagged, LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C), "and a key tag still reads");
    const short = { ...LIVE_LISTING, attributes: LIVE_LISTING.attributes.map((a) => (a.name === "run" ? { ...a, value: "0x12" } : a)) };
    assert.ok("dropped" in decodeRow(short, LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C), "but never a short value");
    const str = { ...LIVE_LISTING, attributes: LIVE_LISTING.attributes.map((a) => (a.name === "run" ? { ...a, type: "str" } : a)) };
    assert.ok("dropped" in decodeRow(str, LISTING_TYPES, Q.LISTING_ATTRS, "anypercent.listing", C), "nor another type");
  });

  it("the web board reads that listing too", async () => {
    const { runInNewContext } = await import("node:vm");
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    const js = html.split("<script>")[1].split("</script>")[0].split("// ---- State")[0];
    const page = runInNewContext(`${js}\n;({ decodeAll, LISTING_TYPES, LISTING_REQUIRED, CHECKER })`, { BigInt, Number, document: {}, location: {} }) as {
      decodeAll: (d: unknown[], t: unknown, r: unknown, s: string, pin: string) => { rows: Array<Record<string, unknown>>; dropped: number };
      LISTING_TYPES: unknown;
      LISTING_REQUIRED: unknown;
      CHECKER: string;
    };
    const live = { ...LIVE_LISTING, creator: page.CHECKER.toLowerCase() };
    const out = page.decodeAll([live], page.LISTING_TYPES, page.LISTING_REQUIRED, "anypercent.listing", page.CHECKER);
    assert.equal(out.dropped, 0);
    assert.equal(out.rows[0].run, "0x1a7d31fd898939adb76280fdaff8cc5f830c82ef6fd0a00105d4b0d45834cf1d");
  });

  it("drops and counts: a foreign creator, another schema, a missing or mistyped column", () => {
    const rows = [
      good,
      { ...good, creator: "0x2222222222222222222222222222222222222222" },
      { ...good, attributes: good.attributes.map((a) => (a.name === "arkiv.schema" ? { ...a, value: "anypercent.smoke.run" } : a)) },
      { ...good, attributes: good.attributes.filter((a) => a.name !== "frames") },
      { ...good, attributes: good.attributes.map((a) => (a.name === "human" ? { name: "human", type: "str", value: "true" } : a)) },
      { ...good, attributes: good.attributes.map((a) => (a.name === "frames" ? { name: "frames", type: "u64", value: 6170 } : a)) },
      { creator: C_LOWER },
    ];
    const page = decodePage(rows, RUN_TYPES, asked, "anypercent.run", C);
    assert.equal(page.rows.length, 1);
    assert.equal(page.dropped, 6);
  });

  it("without a pin (Q8) foreign rows are kept, with their creator", () => {
    const page = decodePage([good, { ...good, creator: "0x2222222222222222222222222222222222222222" }], RUN_TYPES, asked, "anypercent.run", null);
    assert.equal(page.rows.length, 2);
    assert.equal(page.rows[1].creator, "0x2222222222222222222222222222222222222222");
  });

  it("a ghost read needs exactly one of log and log_enc", () => {
    const withBoth = { ...good, attributes: [...good.attributes, { name: "tool", type: "str", value: "t" }, { name: "season", type: "i32", value: 1 }, { name: "log", type: "bytes", value: "0x00" }, { name: "log_enc", type: "bytes", value: "0x00" }] };
    const ask = [...Q.RUN_ALL_ATTRS, "log", "log_enc"];
    assert.ok("dropped" in decodeRow(withBoth, RUN_TYPES, ask, "anypercent.run", C));
    const neither = { ...withBoth, attributes: withBoth.attributes.filter((a) => a.name !== "log" && a.name !== "log_enc") };
    assert.ok("dropped" in decodeRow(neither, RUN_TYPES, ask, "anypercent.run", C));
    const one = { ...withBoth, attributes: withBoth.attributes.filter((a) => a.name !== "log") };
    const r = decodeRow(one, RUN_TYPES, ask, "anypercent.run", C);
    assert.ok("row" in r && r.row.values.log_enc instanceof Uint8Array);
  });
});

describe("the service's real port reads live-shaped rows", () => {
  it("SdkArkiv.liveListingFor finds a listing whose run comes back tagged bytes32 (the dedupe depends on it)", async () => {
    const { SdkArkiv } = await import("../src/arkiv/client.js");
    const runKey = `0x${"1a7d".repeat(16)}`;
    const sent: string[] = [];
    class Stub extends SdkArkiv {
      override async query(query: string) {
        sent.push(query);
        const attributes = [
          { name: "arkiv.schema", type: "str", value: "anypercent.listing" },
          { name: "run", type: "bytes32", value: runKey },
          { name: "game", type: "str", value: "MDGP" },
          { name: "season", type: "i32", value: 1 },
          { name: "frames", type: "u64", value: "0x181a" },
          { name: "log_h", type: "str", value: H },
          { name: "price", type: "dec", value: "0.1" },
          { name: "seller", type: "str", value: "5a5a5a5a5a5a5a5a" },
          { name: "book", type: "str", value: "ANY-6PS" },
          { name: "human", type: "bool", value: true },
        ];
        return { data: [{ key: K, creator: C_LOWER, expiresAt: "0x10", attributes }], blockNumber: 1n };
      }
    }
    const port = new Stub({ rpcUrl: "http://127.0.0.1:9", accessKey: "unused-in-tests", checkerAddress: C });
    const l = await port.liveListingFor(runKey, C);
    assert.equal(sent[0], Q.qListingForRun(runKey, C));
    assert.equal(l?.key, K);
    assert.equal(l?.run, runKey);
    assert.equal(l?.price, "0.1");
  });
});

describe("the real port reads a console's entity and the checker's stamp (console-owned records)", () => {
  const W = "0xA1a1a1A1a1a1a1a1a1A1a1a1a1a1a1a1a1a1a1A1"; // a console wallet, as the node checksums it

  it("SdkArkiv.getEntity: any creator, the flags, the schema tag, every attribute typed as toSdkValues types it", async () => {
    const { SdkArkiv } = await import("../src/arkiv/client.js");
    const { toSdkValues } = await import("../src/arkiv/schema.js");
    const { createServer } = await import("node:http");
    const runKey = `0x${"1a7d".repeat(16)}`;
    const asked: Array<{ method: string; params: string[] }> = [];
    const reply = {
      key: K,
      owner: W.toLowerCase(),
      creator: W.toLowerCase(),
      expiresAt: "0x41eee8",
      creationFlags: { readonly: true, permissionlessExtension: false, raw: 1 },
      attributes: [
        { name: "arkiv.schema", type: "str", value: "anypercent.listing" },
        { name: "run", type: "bytes32", value: runKey },
        { name: "game", type: "str", value: "MDGP" },
        { name: "season", type: "i32", value: 1 },
        { name: "frames", type: "u64", value: "0x181a" },
        { name: "log_h", type: "str", value: H },
        { name: "price", type: "dec", value: "0.1" },
        { name: "seller", type: "str", value: "5a5a5a5a5a5a5a5a" },
        { name: "book", type: "str", value: "ANY-6PS" },
        { name: "human", type: "bool", value: true },
      ],
    };
    // A node on loopback that answers arkiv_getEntity as Rabdi does (null for no live entity).
    const node = createServer((req, res) => {
      let raw = "";
      req.on("data", (c) => (raw += c));
      req.on("end", () => {
        const call = JSON.parse(raw) as { id: number; method: string; params: string[] };
        asked.push(call);
        res.setHeader("content-type", "application/json");
        const withPayload = `0x${"7".repeat(64)}`;
        const result = call.params[0] === K ? reply : call.params[0] === withPayload ? { ...reply, key: withPayload, payload: "0x1234", contentType: "text/plain" } : null;
        res.end(JSON.stringify({ jsonrpc: "2.0", id: call.id, result }));
      });
    });
    await new Promise<void>((r) => node.listen(0, "127.0.0.1", r));
    try {
      const { port: p } = node.address() as { port: number };
      const port = new SdkArkiv({ rpcUrl: `http://127.0.0.1:${p}`, accessKey: "unused-in-tests", checkerAddress: C });
      const e = await port.getEntity(K);
      assert.equal(asked[0].method, "arkiv_getEntity");
      assert.ok(e);
      assert.deepEqual([e.key, e.creator, e.owner, e.expiresAt, e.schema], [K, W.toLowerCase(), W.toLowerCase(), 4_321_000n, "anypercent.listing"]);
      assert.deepEqual(e.flags, { readonly: true, permissionlessExtension: false });
      assert.equal("arkiv.schema" in e.values, false);
      const want = toSdkValues("listing", { run: runKey, game: "MDGP", season: 1, frames: 6170, log_h: H, price: "0.1", seller: "5a5a5a5a5a5a5a5a", book: "ANY-6PS", human: true }) as Record<string, { type: string; value: unknown }>;
      assert.deepEqual(Object.keys(e.values).sort(), Object.keys(want).sort());
      for (const [name, w] of Object.entries(want)) {
        const got: { type: string; value: unknown } = e.values[name];
        assert.equal(got.type, w.type, name);
        assert.equal(typeof got.value === "string" ? got.value.toLowerCase() : got.value, typeof w.value === "string" ? w.value.toLowerCase() : w.value, name);
      }
      assert.equal(await port.getEntity(`0x${"9".repeat(64)}`), null, "no live entity: null");
      assert.equal(e.payload, false, "an anypercent entity carries no payload");
      assert.equal((await port.getEntity(`0x${"7".repeat(64)}`))?.payload, true, "a payload or content type the node reports is seen (publish refuses it)");
      assert.equal(asked.length, 3, "one request per entity");
    } finally {
      await new Promise<void>((r) => node.close(() => r()));
    }
  });

  it("SdkArkiv.stampByLogHash: Q7 on stamps, pinned to the checker, decoded with its console and copied splits", async () => {
    const { SdkArkiv } = await import("../src/arkiv/client.js");
    const runKey = `0x${"1a7d".repeat(16)}`;
    const sent: string[] = [];
    class Stub extends SdkArkiv {
      override async query(query: string) {
        sent.push(query);
        const attributes = [
          { name: "arkiv.schema", type: "str", value: "anypercent.stamp" },
          { name: "run", type: "bytes32", value: runKey },
          { name: "console", type: "str", value: W.toLowerCase() },
          { name: "game", type: "str", value: "MDGP" },
          { name: "season", type: "i32", value: 1 },
          { name: "frames", type: "u64", value: "0x181a" },
          { name: "log_h", type: "str", value: H },
          { name: "book", type: "str", value: "ANY-6PS" },
          { name: "human", type: "bool", value: true },
          { name: "s1", type: "u64", value: "0x827" },
          { name: "s2", type: "u64", value: "0x7cb" },
          { name: "s3", type: "u64", value: "0x828" },
          { name: "split_kind", type: "str", value: "lap" },
          { name: "final_hash", type: "u64", value: "0x225d59fd" },
          { name: "tool", type: "str", value: "arcade_replay sha256:a992006e6280" },
        ];
        return { data: [{ key: K, creator: C_LOWER, expiresAt: "0x10", attributes }], blockNumber: 1n };
      }
    }
    const port = new Stub({ rpcUrl: "http://127.0.0.1:9", accessKey: "unused-in-tests", checkerAddress: C });
    const st = await port.stampByLogHash(H);
    assert.equal(sent[0], Q.qStampByLogHash(H, C));
    assert.equal(sent[0], `arkiv.schema = str('anypercent.stamp') AND log_h = str('${H}') AND $creator = addr(${C})`);
    assert.ok(st);
    assert.deepEqual([st.run, st.console, st.book, st.frames, st.final_hash, st.splits], [runKey, W.toLowerCase(), "ANY-6PS", 6170n, 576543229n, [2087, 1995, 2088]]);
  });

  it("Q7 on stamps renders as the SDK's own builder would", () => {
    const sel = () => createPublicClient({ chain: rabdi({ accessKey: "x" }), transport: custom({ request: async () => null }) }).select({ $key: true });
    return import("../src/arkiv/schema.js").then(({ Stamp }) => {
      assert.equal(sel().from(Stamp).where(eq("log_h", str(H))).createdBy(C).toString(), Q.qStampByLogHash(H, C));
    });
  });
});
