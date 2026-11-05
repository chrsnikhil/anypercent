/**
 * Q1-Q9 (spec: Queries), as functions returning the exact strings every reader sends to
 * `arkiv_query`: the console (launcher handler/arkiv_rpc.py), the web board (public/board.html), the
 * service and the scripts. They render exactly as the SDK's own query builder would (a test checks
 * that), so a stranger can paste one into curl and get the board.
 *
 * - `C` is the checker's address, always written in its EIP-55 form, as `npm run arkiv:keygen`
 *   prints it and /arkiv/config returns it.
 * - Every reader pins `$creator = addr(C)`: rows anyone else writes never reach a board (Q8 is the
 *   one query without the pin, for the look-alike demo).
 * - Every input is checked before it goes into a string, so nothing can widen a query.
 *
 * The smoke script runs the same queries against the anypercent.smoke.* twins.
 */
import { getAddress } from "viem";
import { GAME_IDS, REAL, type SchemaNames } from "./schema.js";

/** Q1 as a template, exactly as board.html and the launcher write it (a test checks both). */
export const Q1_TEMPLATE =
  "arkiv.schema = str('anypercent.run') AND game = str('${game}') AND season = i32(${season}) AND $creator = addr(${checker}) ORDER BY frames:u64 ASC";

/** What a run board selects: never `log` or `log_enc` (only one ghost at a time selects those). */
export const RUN_BOARD_ATTRS = ["game", "title", "frames", "runner", "book", "label", "human", "credential", "log_h", "rules"] as const;
export const LISTING_ATTRS = ["run", "game", "season", "frames", "log_h", "price", "seller", "book", "human"] as const;
export const RUN_ALL_ATTRS = [...RUN_BOARD_ATTRS, "season", "tool"] as const;
export const SCHEMA_ATTR = "arkiv.schema";
/** A page holds at most this many rows (the node's maximum). */
export const PAGE = 100;

export const GAME_RE = /^[A-Z0-9]{4}$/;
export const BOOK_RE = /^ANY-[A-Z0-9]{3,8}$/;
export const KEY_RE = /^0x[0-9a-fA-F]{64}$/;
export const LOG_H_RE = /^[0-9a-f]{64}$/;
export const RUNNER_RE = /^[0-9a-f]{16}$/;

class QueryInputError extends Error {}

function need(ok: boolean, what: string): void {
  if (!ok) throw new QueryInputError(`bad query input: ${what}`);
}

/** The checker as the queries write it: EIP-55. */
export function checksum(address: string): string {
  need(/^0x[0-9a-fA-F]{40}$/.test(address), "address");
  return getAddress(address);
}

const sv = (v: string) => `str('${v.replaceAll("'", "''")}')`;

function game(g: string): string {
  need(GAME_RE.test(g), "game");
  return g;
}
function season(s: number): number {
  need(Number.isInteger(s) && s >= -2_147_483_648 && s <= 2_147_483_647, "season");
  return s;
}
function entityKey(k: string): string {
  need(KEY_RE.test(k), "key");
  return k.toLowerCase();
}

/** Q1: the run board of one game and season, fastest first. */
export function q1Board(g: string, s: number, checker: string, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.run)} AND game = ${sv(game(g))} AND season = i32(${season(s)}) AND $creator = addr(${checksum(checker)}) ORDER BY frames:u64 ASC`;
}

/** Q2: the live listings of one game and season, fastest first. */
export function q2Listings(g: string, s: number, checker: string, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.listing)} AND game = ${sv(game(g))} AND season = i32(${season(s)}) AND $creator = addr(${checksum(checker)}) ORDER BY frames:u64 ASC`;
}

/** Q3: the listed ghost just ahead of `frames` (limit 1). */
export function q3JustAhead(g: string, s: number, frames: number | bigint, checker: string, names: SchemaNames = REAL): string {
  const f = BigInt(frames);
  need(f >= 0n && f < 2n ** 64n, "frames");
  return `arkiv.schema = ${sv(names.listing)} AND game = ${sv(game(g))} AND season = i32(${season(s)}) AND frames < u64(${f}) AND $creator = addr(${checksum(checker)}) ORDER BY frames:u64 DESC`;
}

/** Q4: one record book's runs (the profile): times, HUMAN and credential. */
export function q4BookRuns(book: string, checker: string, names: SchemaNames = REAL): string {
  need(BOOK_RE.test(book), "book");
  return `arkiv.schema = ${sv(names.run)} AND book = ${sv(book)} AND $creator = addr(${checksum(checker)}) ORDER BY frames:u64 ASC`;
}

/** Q4, by runner id instead of book. */
export function q4RunnerRuns(runner: string, checker: string, names: SchemaNames = REAL): string {
  need(RUNNER_RE.test(runner), "runner");
  return `arkiv.schema = ${sv(names.run)} AND runner = ${sv(runner)} AND $creator = addr(${checksum(checker)}) ORDER BY frames:u64 ASC`;
}

/** Q5: one record book's listed ghosts, soonest to end first. */
export function q5BookListings(book: string, checker: string, names: SchemaNames = REAL): string {
  need(BOOK_RE.test(book), "book");
  return `arkiv.schema = ${sv(names.listing)} AND book = ${sv(book)} AND $creator = addr(${checksum(checker)}) ORDER BY $expiresAt:u64 ASC`;
}

/** Q6: one listing by key (check_listing). */
export function q6Listing(key: string, checker: string, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.listing)} AND $key = key(${entityKey(key)}) AND $creator = addr(${checksum(checker)})`;
}

/** Q6 on runs: one run by key (check_listing; a plain ghost selects `log`). */
export function q6Run(key: string, checker: string, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.run)} AND $key = key(${entityKey(key)}) AND $creator = addr(${checksum(checker)})`;
}

/** Q7: the live run with this log, if any (the service's dedupe before a write; limit 1). */
export function q7RunByLogHash(logH: string, checker: string, names: SchemaNames = REAL): string {
  need(LOG_H_RE.test(logH), "log_h");
  return `arkiv.schema = ${sv(names.run)} AND log_h = ${sv(logH)} AND $creator = addr(${checksum(checker)})`;
}

/** Q8: Q1 without the `$creator` pin (select `creator`): the look-alike demo. */
export function q8AnyWallet(g: string, s: number, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.run)} AND game = ${sv(game(g))} AND season = i32(${season(s)}) ORDER BY frames:u64 ASC`;
}

/** Q9: Q1 with `human = true`: the web board's "HUMAN only" filter. */
export function q9Human(g: string, s: number, checker: string, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.run)} AND game = ${sv(game(g))} AND season = i32(${season(s)}) AND human = true AND $creator = addr(${checksum(checker)}) ORDER BY frames:u64 ASC`;
}

/** The service's own: the live listing of one run (dedupe: write a listing only when none is live). */
export function qListingForRun(runKey: string, checker: string, names: SchemaNames = REAL): string {
  return `arkiv.schema = ${sv(names.listing)} AND run = key(${entityKey(runKey)}) AND $creator = addr(${checksum(checker)})`;
}

/** The `select` of an arkiv_query request (RpcSelect). */
export interface RpcSelect {
  key?: boolean;
  owner?: boolean;
  creator?: boolean;
  expiresAt?: boolean;
  attributes?: Record<string, boolean>;
  count?: boolean;
}

/** key, creator, expiresAt, `arkiv.schema` and these attributes. */
export function selectOf(attrs: readonly string[], opts: { count?: boolean; owner?: boolean } = {}): RpcSelect {
  const attributes: Record<string, boolean> = { [SCHEMA_ATTR]: true };
  for (const a of attrs) attributes[a] = true;
  return {
    key: true,
    creator: true,
    expiresAt: true,
    ...(opts.owner ? { owner: true } : {}),
    attributes,
    ...(opts.count ? { count: true } : {}),
  };
}

/** The params of one `arkiv_query` call. */
export function queryParams(query: string, select: RpcSelect, limit = PAGE): [string, { select: RpcSelect; limit: string }] {
  return [query, { select, limit: `0x${limit.toString(16)}` }];
}

export const ARCADE_GAMES = GAME_IDS;
