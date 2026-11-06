/**
 * The console's schema copy (schemas.mjs) against the bridge's source of truth (schema.ts): every run and listing
 * column with its type, index and optional flag, the schema names, and what toSdkValues makes of the same values.
 * Any drift fails here, so the run a console writes is the run the bridge issued and checks back.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { COLUMN_DEFS, LISTING_SCHEMA, Listing, Run, RUN_SCHEMA, toSdkValues } from "../schemas.mjs";
import { bridgeSchema } from "./bridge.mjs";

const bridge = await bridgeSchema();

const RUN_VALUES = {
  game: "MDGP",
  title: "MARINE DRIVE GP",
  season: 1,
  rules: 3,
  frames: 5025,
  log_h: "a".repeat(64),
  runner: "r_0123456789abcdef",
  book: "ANY-6PS",
  human: true,
  credential: "orb",
  tool: "arcade_replay 1",
  log_enc: Uint8Array.from([0, 1, 2, 250, 255]),
  s1: 1200,
  s2: 1300,
  s3: 1250,
  s4: 1275,
  split_kind: "lap",
};
const BOT_RUN_VALUES = { ...RUN_VALUES, book: undefined, label: "BOT-1", human: false, credential: undefined, log_enc: undefined, log: Uint8Array.from([9, 8, 7]), gen: "seeded", frames: 2n ** 63n };
const LISTING_VALUES = {
  run: "0x" + "b".repeat(64),
  game: "MDGP",
  season: 1,
  frames: 5025,
  log_h: "a".repeat(64),
  price: "0.1",
  seller: "ANY-6PS",
  book: "ANY-6PS",
  human: true,
  pay_to: "0.0.12345",
  hcs: "0.0.777/12",
};

test("every run and listing column is the bridge's (type, indexed, optional)", () => {
  assert.deepEqual(COLUMN_DEFS.run, bridge.COLUMN_DEFS.run);
  assert.deepEqual(COLUMN_DEFS.listing, bridge.COLUMN_DEFS.listing);
  assert.deepEqual(Object.keys(COLUMN_DEFS.run), Object.keys(bridge.COLUMN_DEFS.run));
  assert.deepEqual(Object.keys(COLUMN_DEFS.listing), Object.keys(bridge.COLUMN_DEFS.listing));
});

test("the schema names are the bridge's, and the SDK schemas carry them", () => {
  assert.equal(RUN_SCHEMA, bridge.RUN_SCHEMA);
  assert.equal(LISTING_SCHEMA, bridge.LISTING_SCHEMA);
  assert.equal(Run.name, bridge.Run.name);
  assert.equal(Listing.name, bridge.Listing.name);
});

test("toSdkValues makes what the bridge's makes of the same values", () => {
  assert.deepEqual(toSdkValues("run", RUN_VALUES), bridge.toSdkValues("run", RUN_VALUES));
  assert.deepEqual(toSdkValues("run", BOT_RUN_VALUES), bridge.toSdkValues("run", BOT_RUN_VALUES));
  assert.deepEqual(toSdkValues("listing", LISTING_VALUES), bridge.toSdkValues("listing", LISTING_VALUES));
  assert.deepEqual(toSdkValues("listing", { ...LISTING_VALUES, frames: 7n, price: 0.25 }), bridge.toSdkValues("listing", { ...LISTING_VALUES, frames: 7n, price: 0.25 }));
});

test("a column neither knows is refused by both", () => {
  assert.throws(() => toSdkValues("run", { ...RUN_VALUES, nickname: "x" }), /unknown column nickname/);
  assert.throws(() => bridge.toSdkValues("run", { ...RUN_VALUES, nickname: "x" }), /unknown column nickname/);
  assert.throws(() => toSdkValues("listing", { ...LISTING_VALUES, title: "x" }), /unknown column title/);
  assert.throws(() => bridge.toSdkValues("listing", { ...LISTING_VALUES, title: "x" }), /unknown column title/);
});
