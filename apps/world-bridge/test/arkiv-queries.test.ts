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
    assert.equal(Q.Q1_TEMPLATE.replace("${game}", "MDGP").replace("${season}", "1").replace("${checker}", C), Q.q1Board("MDGP", 1, C));
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
    assert.equal(addr(C_LOWER).value, C);
  });
});

describe("the web board", () => {
  it("public/board.html carries Q1's exact template", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    assert.ok(html.includes(Q.Q1_TEMPLATE), "board.html must contain Q1 exactly");
  });
  it("and every other query it runs, in the same words", () => {
    const html = readFileSync(join(appDir, "public", "board.html"), "utf8");
    const tpl = (s: string) =>
      s.replace("'MDGP'", "'${game}'").replace("i32(1)", "i32(${season})").replace(`addr(${C})`, "addr(${checker})");
    for (const q of [Q.q2Listings("MDGP", 1, C), Q.q8AnyWallet("MDGP", 1), Q.q9Human("MDGP", 1, C)]) {
      assert.ok(html.includes(tpl(q)), `board.html misses ${tpl(q)}`);
    }
    assert.ok(html.includes(tpl(Q.q3JustAhead("MDGP", 1, 6290, C)).replace("u64(6290)", "u64(${frames})")));
    assert.ok(html.includes(Q.q4BookRuns("ANY-6PS", C).replace("'ANY-6PS'", "'${book}'").replace(`addr(${C})`, "addr(${checker})")));
    assert.ok(html.includes(Q.q5BookListings("ANY-6PS", C).replace("'ANY-6PS'", "'${book}'").replace(`addr(${C})`, "addr(${checker})")));
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
