/** SpecJSON: the issued run and listing as plain JSON, and back, exactly (Uint8Array, bigint, Date). */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { CreateSpec, ListingValues, RunValues } from "../src/arkiv/client.js";
import { LISTING_FLAGS, RUN_FLAGS } from "../src/arkiv/schema.js";
import { fromSpecJson, SpecJsonError, toSpecJson } from "../src/arkiv/spec-json.js";

const RUN: CreateSpec<RunValues> = {
  values: {
    game: "MDGP",
    title: "MARINE DRIVE GP",
    season: 1,
    rules: 4,
    frames: 6170,
    log_h: "ab".repeat(32),
    runner: "0123456789abcdef",
    book: "ANY-6PS",
    human: true,
    credential: "Orb",
    tool: "arcade_replay sha256:a992006e6280",
    log_enc: Uint8Array.from([0, 1, 2, 250, 251, 252, 253, 254, 255]),
    s1: 2087,
    s2: 1995,
    s3: 2088,
    split_kind: "lap",
  },
  flags: { ...RUN_FLAGS },
  expiry: { kind: "atDate", date: new Date("2027-01-30T00:00:00.000Z"), atLeastDays: 1 },
};

const LISTING: CreateSpec<ListingValues> = {
  values: { game: "MDGP", season: 1, frames: 6170, log_h: "ab".repeat(32), price: "0.1", seller: "0123456789abcdef", book: "ANY-6PS", human: true, pay_to: "0.0.5123456", hcs: "0.0.8001/41" },
  flags: { ...LISTING_FLAGS },
  expiry: { kind: "days", days: 7 },
};

describe("SpecJSON", () => {
  it("round trips a run spec exactly: the bytes stay a Uint8Array, the date a Date", () => {
    const json = toSpecJson(RUN);
    const back = fromSpecJson<RunValues>(JSON.parse(JSON.stringify(json)));
    assert.deepEqual(back, RUN);
    assert.ok(back.values.log_enc instanceof Uint8Array);
    assert.ok((back.expiry as { date: Date }).date instanceof Date);
  });

  it("round trips a listing spec and a bigint (an atBlock expiry, a u64 given as a bigint)", () => {
    assert.deepEqual(fromSpecJson(JSON.parse(JSON.stringify(toSpecJson(LISTING)))), LISTING);
    const big: CreateSpec<Record<string, unknown>> = { values: { frames: 18446744073709551615n, n: -3n }, flags: { readonly: true, permissionlessExtension: false }, expiry: { kind: "atBlock", block: 1_200_000n } };
    const back = fromSpecJson(JSON.parse(JSON.stringify(toSpecJson(big))));
    assert.deepEqual(back, big);
    assert.equal(typeof back.values.frames, "bigint");
  });

  it("encodes bytes as {$bytes: base64}, bigint as {$big}, a Date as {$date: ISO}", () => {
    const json = toSpecJson(RUN) as unknown as { values: Record<string, unknown>; expiry: Record<string, unknown> };
    assert.deepEqual(json.values.log_enc, { $bytes: Buffer.from(RUN.values.log_enc!).toString("base64") });
    assert.deepEqual(json.expiry, { kind: "atDate", date: { $date: "2027-01-30T00:00:00.000Z" }, atLeastDays: 1 });
    const big = toSpecJson({ values: { v: 123n }, flags: { readonly: true, permissionlessExtension: true }, expiry: { kind: "atBlock", block: 7n } }) as unknown as Record<string, Record<string, unknown>>;
    assert.deepEqual(big.values.v, { $big: "123" });
    assert.deepEqual(big.expiry.block, { $big: "7" });
  });

  it("leaves an undefined value out, as JSON does", () => {
    const json = toSpecJson({ ...LISTING, values: { ...LISTING.values, pay_to: undefined } }) as unknown as { values: Record<string, unknown> };
    assert.equal("pay_to" in json.values, false);
  });

  it("decodes a JSON string as well as a parsed object", () => {
    assert.deepEqual(fromSpecJson(JSON.stringify(toSpecJson(RUN))), RUN);
  });

  it("refuses what it cannot read back exactly", () => {
    const good = JSON.parse(JSON.stringify(toSpecJson(RUN)));
    const bad = (mut: (j: any) => void) => {
      const j = structuredClone(good);
      mut(j);
      return j;
    };
    for (const [what, j] of [
      ["an unknown tag", bad((j) => (j.values.log_enc = { $hex: "00" }))],
      ["a tag with company", bad((j) => (j.values.log_enc = { $bytes: "AAE=", x: 1 }))],
      ["bytes that are not base64", bad((j) => (j.values.log_enc = { $bytes: "not base64!" }))],
      ["a big that is not an integer", bad((j) => (j.values.frames = { $big: "1.5" }))],
      ["a date that is not ISO", bad((j) => (j.expiry.date = { $date: "tomorrow" }))],
      ["no values", bad((j) => delete j.values)],
      ["flags that are not booleans", bad((j) => (j.flags.readonly = "yes"))],
      ["an unknown expiry kind", bad((j) => (j.expiry.kind = "forever"))],
      ["not JSON", "{"],
    ] as const) {
      assert.throws(() => fromSpecJson(j), SpecJsonError, what);
    }
  });

  it("refuses to encode what JSON cannot hold", () => {
    assert.throws(() => toSpecJson({ values: { frames: Number.NaN }, flags: { readonly: true, permissionlessExtension: true }, expiry: { kind: "days", days: 1 } }), SpecJsonError);
    assert.throws(() => toSpecJson({ values: { $x: 1 }, flags: { readonly: true, permissionlessExtension: true }, expiry: { kind: "days", days: 1 } }), SpecJsonError);
  });
});
