/**
 * The two Arkiv entities, as SDK 1.0.1 named schemas. A named schema tags every row it creates with
 * an indexed `arkiv.schema` str, and every reader filters on it (spec: Entities).
 *
 * - anypercent.run: one checked run (the checker replayed its log before writing it).
 * - anypercent.listing: a World-approved offer of one run's ghost. Two optional columns came with
 *   the Hedera module: `pay_to` (the seller's Hedera account, exactly as World App showed it in the
 *   approved text; absent: not for sale) and `hcs` (`<topic>/<sequence number>` of the LISTING
 *   message; absent when Hedera was off). Rows written before them still fit the schema.
 *
 * Splits and the house (scout and pivot): a run row may carry its lap splits, `s1`..`s4` (u64,
 * indexed, contiguous from s1, summing to `frames`) with `split_kind` "lap", and a BOT row carries
 * `gen` (how the log was made). A listing has exactly one of `book` (a person's World-approved
 * listing) and `label` (the house's: `human` false, `pay_to` the house account). Every column added
 * here is optional, so every row written before still fits.
 *
 * The anypercent.smoke.* twins have the same columns; only `npm run arkiv:smoke` writes them, with a
 * one-hour expiry, and deletes them again.
 *
 * Nothing about a person goes in either: no names, faces, raw World ids, device ids or free text.
 */
import { bool, bytes, dec, defineSchema, i32, key, str, u64 } from "@arkiv-network/sdk/schema";

export const RUN_SCHEMA = "anypercent.run";
export const LISTING_SCHEMA = "anypercent.listing";
export const SMOKE_RUN_SCHEMA = "anypercent.smoke.run";
export const SMOKE_LISTING_SCHEMA = "anypercent.smoke.listing";

/** The arcade games, by id, with the title World App shows for a listing. */
export const GAMES: Record<string, string> = {
  SHIP: "SHIP IT!",
  MDGP: "MARINE DRIVE GP",
  RUSH: "RUSH HOUR",
  SEGF: "SEGFAULT",
  ZIPG: "ZIP",
};
export const GAME_IDS = Object.keys(GAMES);

/** Listings end after this many days (the launcher's LISTING_DAYS). */
export const LISTING_DAYS = 7;

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
export const SmokeRun = defineSchema(SMOKE_RUN_SCHEMA, runColumns());
export const SmokeListing = defineSchema(SMOKE_LISTING_SCHEMA, listingColumns());

export type RunSchema = typeof Run;
export type ListingSchema = typeof Listing;

/** Which pair of schemas a reader or writer works on: the real ones, or the smoke twins. */
export interface SchemaNames {
  run: string;
  listing: string;
}
export const REAL: SchemaNames = { run: RUN_SCHEMA, listing: LISTING_SCHEMA };
export const SMOKE: SchemaNames = { run: SMOKE_RUN_SCHEMA, listing: SMOKE_LISTING_SCHEMA };

/** The column types, for the raw readers' validation (the SDK checks these itself). */
export const RUN_TYPES: Record<string, { type: string; required: boolean }> = {
  game: { type: "str", required: true },
  title: { type: "str", required: true },
  season: { type: "i32", required: true },
  rules: { type: "u64", required: true },
  frames: { type: "u64", required: true },
  log_h: { type: "str", required: true },
  runner: { type: "str", required: true },
  book: { type: "str", required: false },
  label: { type: "str", required: false },
  human: { type: "bool", required: true },
  credential: { type: "str", required: false },
  tool: { type: "str", required: true },
  log: { type: "bytes", required: false },
  log_enc: { type: "bytes", required: false },
  s1: { type: "u64", required: false },
  s2: { type: "u64", required: false },
  s3: { type: "u64", required: false },
  s4: { type: "u64", required: false },
  split_kind: { type: "str", required: false },
  gen: { type: "str", required: false },
};
export const LISTING_TYPES: Record<string, { type: string; required: boolean }> = {
  run: { type: "key", required: true },
  game: { type: "str", required: true },
  season: { type: "i32", required: true },
  frames: { type: "u64", required: true },
  log_h: { type: "str", required: true },
  price: { type: "dec", required: true },
  seller: { type: "str", required: true },
  book: { type: "str", required: false },
  label: { type: "str", required: false },
  human: { type: "bool", required: true },
  pay_to: { type: "str", required: false },
  hcs: { type: "str", required: false },
};

/** The split columns, in order. */
export const SPLIT_COLUMNS = ["s1", "s2", "s3", "s4"] as const;
/** The one kind of split this build writes: MDGP's laps. */
export const SPLIT_KIND = "lap";

/** Flags and expiry, by entity (spec: Entities). */
export const RUN_FLAGS = { readonly: true, permissionlessExtension: true } as const;
export const LISTING_FLAGS = { readonly: true, permissionlessExtension: false } as const;
