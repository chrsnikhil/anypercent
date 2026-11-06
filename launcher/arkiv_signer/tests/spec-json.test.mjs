/**
 * The signer's SpecJSON decoder against the bridge's (spec-json.ts), on shared fixtures: every document both
 * read gives the same spec (Uint8Array, bigint and Date included), every document the bridge refuses the console
 * refuses too, and what the bridge encodes the console decodes back exactly.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fromSpecJson, SpecJsonError } from "../signer.mjs";
import { bridgeSpecJson } from "./bridge.mjs";

const bridge = await bridgeSpecJson();
const FIXTURES = JSON.parse(readFileSync(new URL("./fixtures/spec-json.json", import.meta.url), "utf8"));
const input = (c) => ("text" in c ? c.text : c.doc);

for (const c of FIXTURES.valid) {
  test(`decodes as the bridge does: ${c.name}`, () => {
    const ours = fromSpecJson(input(c));
    assert.deepStrictEqual(ours, bridge.fromSpecJson(input(c)));
  });
}

for (const c of FIXTURES.invalid) {
  test(`refuses what the bridge refuses: ${c.name}`, () => {
    assert.throws(() => bridge.fromSpecJson(input(c)), bridge.SpecJsonError);
    assert.throws(() => fromSpecJson(input(c)), SpecJsonError);
  });
}

test("the three tags come back as the values the bridge encoded", () => {
  const spec = {
    values: { frames: 2n ** 64n - 1n, log_enc: Uint8Array.from([0, 255, 7]), game: "ZIPG", human: false, s1: undefined },
    flags: { readonly: true, permissionlessExtension: true },
    expiry: { kind: "atDate", date: new Date("2027-01-30T12:34:56.789Z"), atLeastDays: 1 },
  };
  const wire = JSON.parse(JSON.stringify(bridge.toSpecJson(spec)));
  const { s1, ...values } = spec.values;
  assert.deepStrictEqual(fromSpecJson(wire), { ...spec, values });
  assert.deepStrictEqual(fromSpecJson(JSON.stringify(wire)), { ...spec, values });
  const block = { ...spec, expiry: { kind: "atBlock", block: 99n } };
  assert.deepStrictEqual(fromSpecJson(bridge.toSpecJson(block)), { ...block, values });
});

test("every fixture is one the bridge itself reads or refuses (the fixtures test something)", () => {
  assert.ok(FIXTURES.valid.length >= 5 && FIXTURES.invalid.length >= 15);
  const tags = JSON.stringify(FIXTURES.valid);
  for (const tag of ["$bytes", "$big", "$date"]) assert.ok(tags.includes(tag), tag);
});
