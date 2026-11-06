/**
 * The console's copy of the bridge's run and listing schemas (apps/world-bridge/src/arkiv/schema.ts): the
 * columns, the SDK 1.0.1 named schemas built from them, COLUMN_DEFS (the columns as plain data) and
 * toSdkValues (plain values -> the SDK's typed values). The console signs exactly the run and listing the
 * bridge issued, so these must be the bridge's own: tests/schemas.test.mjs loads schema.ts and fails on any
 * drift in a column, its type, index or optional flag, a schema name, or what toSdkValues makes of a value.
 * The console never writes a stamp (the checker does), so the stamp schema is not copied.
 *
 * Edit schema.ts first, then copy the change here; never the other way round.
 */
import { bool, bytes, dec, defineSchema, i32, key, str, u64 } from "@arkiv-network/sdk/schema";

export const RUN_SCHEMA = "anypercent.run";
export const LISTING_SCHEMA = "anypercent.listing";

function runColumns() {
  return {
    game: str().indexed(),
    title: str(),
    season: i32().indexed(),
    rules: u64().indexed(),
    frames: u64().indexed(),
    log_h: str().indexed(),
    runner: str().indexed(),
    book: str().indexed().optional(),
    label: str().optional(),
    human: bool().indexed(),
    credential: str().optional(),
    tool: str(),
    log: bytes().optional(),
    log_enc: bytes().optional(),
    s1: u64().indexed().optional(),
    s2: u64().indexed().optional(),
    s3: u64().indexed().optional(),
    s4: u64().indexed().optional(),
    split_kind: str().optional(),
    gen: str().optional(),
  };
}

function listingColumns() {
  return {
    run: key().indexed(),
    game: str().indexed(),
    season: i32().indexed(),
    frames: u64().indexed(),
    log_h: str().indexed(),
    price: dec().indexed(),
    seller: str().indexed(),
    book: str().indexed().optional(),
    label: str().optional(),
    human: bool().indexed(),
    pay_to: str().indexed().optional(),
    hcs: str().optional(),
  };
}

export const Run = defineSchema(RUN_SCHEMA, runColumns());
export const Listing = defineSchema(LISTING_SCHEMA, listingColumns());

function defsOf(columns) {
  const out = {};
  for (const [name, c] of Object.entries(columns)) out[name] = { type: c.type, indexed: c.isIndexed, optional: c.isOptional };
  return out;
}

/** Every column of a run and a listing as plain data ({type, indexed, optional}), read off the SDK columns. */
export const COLUMN_DEFS = {
  run: defsOf(runColumns()),
  listing: defsOf(listingColumns()),
};

/** A value that does not fit its column (an unknown column, a type this build does not write). */
export class SchemaValueError extends Error {}

/**
 * Plain values -> the SDK's typed values, by the entity's column types: str, i32 (a number), u64 (a number
 * or bigint), bool, dec (its decimal string), key (0x hex) and bytes (a Uint8Array). An undefined value is
 * left out (the column stays unset). `kind` is "run" or "listing".
 */
export function toSdkValues(kind, values) {
  const out = {};
  const defs = COLUMN_DEFS[kind];
  if (!defs) throw new SchemaValueError(`unknown entity ${kind}`);
  for (const [name, v] of Object.entries(values)) {
    if (v === undefined) continue;
    const col = Object.prototype.hasOwnProperty.call(defs, name) ? defs[name] : undefined;
    if (!col) throw new SchemaValueError(`unknown column ${name}`);
    switch (col.type) {
      case "str":
        out[name] = str(v);
        break;
      case "i32":
        out[name] = i32(v);
        break;
      case "u64":
        out[name] = u64(BigInt(v));
        break;
      case "bool":
        out[name] = bool(v);
        break;
      case "dec":
        out[name] = dec(String(v));
        break;
      case "key":
        out[name] = key(v);
        break;
      case "bytes":
        out[name] = bytes(v);
        break;
      default:
        throw new SchemaValueError(`unhandled type ${col.type}`);
    }
  }
  return out;
}
