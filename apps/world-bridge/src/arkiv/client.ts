/**
 * ArkivPort: everything the service asks of Arkiv, behind one interface so the publish pipeline is
 * tested against a fake (test/fake-arkiv.ts) and runs live on the SDK.
 *
 * The real implementation (SdkArkiv) uses @arkiv-network/sdk 1.0.1 on Rabdi:
 * - reads are the exact Q-strings of queries.ts over `arkiv_query`, each row validated like every
 *   other raw reader (rows.ts): stamps pinned to the checker, runs and listings pinned to the
 *   wallet a stamp names, joined by board.ts (a run counts only when a checker stamp names it and
 *   its creator is the stamp's console);
 * - writes go through the SDK's typed schemas (schema.ts), each wallet on its own serial queue (one
 *   wallet, one entity nonce, so a batch's predicted keys hold): the checker writes stamps only,
 *   the house wallet (HOUSE_ARKIV_KEY) the BOT runs and listings;
 * - the access key rides in the RPC URL's last path segment and never reaches a log line: every
 *   error is reduced to a short reason with the key and anything key-shaped removed.
 *
 * Console-owned records (spec: the console owns its records): a player's run and listing are
 * written by the console's own wallet, never here. The checker writes the stamp (`writeStamp`) once
 * `getEntity` read the console's entities back and they were exactly what publish issued.
 * `writeRunAndListing` is the checker-signed path from before; only `npm run arkiv:smoke` (on the
 * smoke twins) still calls it.
 */
import {
  createPublicClient,
  createWalletClient,
  ExpirationTime,
  key as keyValue,
  NoEntityFoundError,
  type PublicArkivClient,
  type WalletArkivClient,
} from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { custom, http, type Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { joinBoard, listingMismatch, runMismatch, stamped } from "./board.js";
import {
  PAGE,
  queryParams,
  qListingForRun,
  q1Board,
  q1Stamps,
  q2Listings,
  q6ListingByKey,
  q6Run,
  q7RunByLogHash,
  qStampByLogHash,
  qStampForRun,
  LISTING_ATTRS,
  RUN_ALL_ATTRS,
  RUN_BOARD_ATTRS,
  SCHEMA_ATTR,
  STAMP_ATTRS,
  selectOf,
  type RpcSelect,
} from "./queries.js";
import { decodePage, splitsOf, type DecodedRow } from "./rows.js";
import { LISTING_TYPES, Listing, REAL, Run, RUN_TYPES, SmokeListing, SmokeRun, SmokeStamp, Stamp, STAMP_TYPES, toSdkValues, type SchemaNames } from "./schema.js";

export { toSdkValues };

const WALLET_RE = /^0x[0-9a-f]{40}$/;

export interface RunRow {
  key: string;
  creator: string | null;
  /** Its `$owner` (lowercase) when the read selected it: a reader counts a run only while owner = creator = its stamp's console. */
  owner?: string | null;
  expiresAt: bigint | null;
  game: string;
  title?: string;
  season?: number;
  rules?: bigint;
  frames: bigint;
  log_h: string;
  runner: string;
  book?: string;
  label?: string;
  human: boolean;
  credential?: string;
  tool?: string;
  log?: Uint8Array;
  log_enc?: Uint8Array;
  /** The lap splits in frames when the row carries splits that check out (rows.splitsOf), else absent. */
  splits?: number[];
}

/**
 * A run that counts (board.ts): a checker stamp names it and its creator is the stamp's console.
 * What every board reader hands on (boardRuns, getRun).
 */
export interface StampedRun extends RunRow {
  /** The wallet that owns the run (lowercase): its creator, the console its stamp names. */
  owner: string;
  /** The checker's stamp that names it. */
  stamp: string;
}

export interface ListingRow {
  key: string;
  creator: string | null;
  /** Its `$owner` (lowercase) when the read selected it: counted only while owner = creator = its run's console. */
  owner?: string | null;
  expiresAt: bigint | null;
  run: string;
  game: string;
  season: number;
  frames: bigint;
  log_h: string;
  price: string;
  seller: string;
  /** A person's listing names its book; the house's names its BOT label instead (exactly one). */
  book?: string;
  label?: string;
  human: boolean;
  /** The seller's Hedera account; absent: not for sale. */
  pay_to?: string;
  /** `<topic>/<seq>` of the LISTING message on HCS. */
  hcs?: string;
}

/** The listing's seller as the console and INTENT name it: its book, or the house's BOT label. */
export function sellerName(l: Pick<ListingRow, "book" | "label">): string {
  return l.book ?? l.label ?? "";
}

/** What a run row is written with (spec: Entities). Exactly one of log and log_enc. */
export interface RunValues {
  game: string;
  title: string;
  season: number;
  rules: number;
  frames: number;
  log_h: string;
  runner: string;
  book?: string;
  label?: string;
  human: boolean;
  credential?: string;
  tool: string;
  log?: Uint8Array;
  log_enc?: Uint8Array;
  /** Lap splits, contiguous from s1, summing to frames (split_kind "lap"). */
  s1?: number;
  s2?: number;
  s3?: number;
  s4?: number;
  split_kind?: string;
  /** BOT rows only: how the log was made. */
  gen?: string;
}

/** The split columns for these splits: {s1, ..., sN, split_kind: "lap"}, or nothing for none. */
export function splitValues(splits: readonly number[] | null | undefined): Pick<RunValues, "s1" | "s2" | "s3" | "s4" | "split_kind"> {
  if (!splits || splits.length === 0) return {};
  const out: Record<string, number | string> = { split_kind: "lap" };
  splits.slice(0, 4).forEach((v, i) => (out[`s${i + 1}`] = v));
  return out as Pick<RunValues, "s1" | "s2" | "s3" | "s4" | "split_kind">;
}

/** What a listing row is written with; its `run` key is filled in by the writer. */
export interface ListingValues {
  game: string;
  season: number;
  frames: number;
  log_h: string;
  /** USDC, as a decimal string ("0.1"). */
  price: string;
  seller: string;
  /** Exactly one of book (a person's listing) and label (the house's). */
  book?: string;
  label?: string;
  human: boolean;
  pay_to?: string;
  hcs?: string;
}

/**
 * What a stamp is written with (spec: Entities, anypercent.stamp): the run it names, the wallet
 * that created that run (lowercase), the run's copied columns, and what replayed it.
 */
export interface StampValues {
  run: string;
  console: string;
  game: string;
  season: number;
  frames: number;
  log_h: string;
  /** Exactly one of book (a person's run) and label (the house's). */
  book?: string;
  label?: string;
  human: boolean;
  s1?: number;
  s2?: number;
  s3?: number;
  s4?: number;
  split_kind?: string;
  /** The replay's final hash as the tool printed it; absent when it printed none. */
  final_hash?: number;
  tool: string;
}

/**
 * The stamp for one run: its key, the console wallet that created it (lowercased here), the copied
 * columns (game, season, frames, log_h, book or label, human, the splits), the replay's final hash
 * (left out when null) and the replay tool's tag.
 */
export function stampValues(run: RunValues, runKey: string, consoleWallet: string, finalHash: number | null, tool: string): StampValues {
  return {
    run: runKey.toLowerCase(),
    console: consoleWallet.toLowerCase(),
    game: run.game,
    season: run.season,
    frames: run.frames,
    log_h: run.log_h,
    ...(run.book !== undefined ? { book: run.book } : {}),
    ...(run.label !== undefined ? { label: run.label } : {}),
    human: run.human,
    ...(run.s1 !== undefined ? { s1: run.s1 } : {}),
    ...(run.s2 !== undefined ? { s2: run.s2 } : {}),
    ...(run.s3 !== undefined ? { s3: run.s3 } : {}),
    ...(run.s4 !== undefined ? { s4: run.s4 } : {}),
    ...(run.split_kind !== undefined ? { split_kind: run.split_kind } : {}),
    ...(finalHash !== null ? { final_hash: finalHash } : {}),
    tool,
  };
}

/** A stamp as the readers decode it. */
export interface StampRow {
  key: string;
  creator: string | null;
  expiresAt: bigint | null;
  run: string;
  console: string;
  game: string;
  season: number;
  frames: bigint;
  log_h: string;
  book?: string;
  label?: string;
  human: boolean;
  /** The copied lap splits when they check out (rows.splitsOf), else absent. */
  splits?: number[];
  final_hash?: bigint;
  tool: string;
}

/** One attribute as the SDK types it: u64 a bigint, i32 a number, key and bytes 0x hex, dec its canonical string. */
export interface TypedValue {
  type: string;
  value: string | number | bigint | boolean;
}

/** One live entity by key, as `arkiv_getEntity` answers: who made it, its flags and every attribute. */
export interface EntityRow {
  key: string;
  /** Lowercase; null when the node did not say. */
  creator: string | null;
  owner: string | null;
  /** The block it expires at. */
  expiresAt: bigint | null;
  /** Its creation flags (fixed for its life), or null when the node did not say. */
  flags: Flags | null;
  /** Its `arkiv.schema` tag, or null when it has none. */
  schema: string | null;
  /** Every other attribute, by name. */
  values: Record<string, TypedValue>;
  /** True when the node reports a payload or a content type on it (an anypercent entity has neither). */
  payload: boolean;
}

/** The chain's clock as `arkiv_getBlockTiming` answers: the current block, its time (s) and the block time (s). */
export interface BlockTiming {
  block: bigint;
  timeS: number;
  durationS: number;
}

/** One house pair: a BOT run and its listing (the listing's `run` is filled in by the writer). */
export interface HousePair {
  run: CreateSpec<RunValues>;
  listing: CreateSpec<ListingValues>;
}

export type ExpirySpec =
  | { kind: "atDate"; date: Date; atLeastDays: number }
  | { kind: "days"; days: number }
  | { kind: "hours"; hours: number }
  | { kind: "atBlock"; block: bigint };

export interface Flags {
  readonly: boolean;
  permissionlessExtension: boolean;
}

export interface CreateSpec<V> {
  values: V;
  flags: Flags;
  expiry: ExpirySpec;
}

export interface Written {
  run: string;
  listing: string;
  tx: string;
}

export interface ArkivPort {
  /** eth_chainId. */
  chainId(): Promise<number>;
  /** An address's balance, in wei of tGLM. */
  balance(address: string): Promise<bigint>;
  /** The chain's clock (turns a date into a block). */
  blockTiming(): Promise<BlockTiming>;
  /** Q7: the live run with this log created by `owner` (a console's or the house's wallet), if any; stamped or not. */
  runByLogHash(logH: string, owner: string): Promise<RunRow | null>;
  /** The live listing of this run created by `owner` (the run's wallet), if any. */
  liveListingFor(runKey: string, owner: string): Promise<ListingRow | null>;
  /** Q7 on stamps: the checker's live stamp of the run with this log, if any. Whether a log is on the board. */
  stampByLogHash(logH: string): Promise<StampRow | null>;
  /** One live entity by key, whoever created it (null: none, deleted or expired). */
  getEntity(key: string): Promise<EntityRow | null>;
  /** One stamp, signed by the checker. */
  writeStamp(spec: CreateSpec<StampValues>): Promise<{ stamp: string; tx: string }>;
  /** Stamps in ONE transaction, signed by the checker (the house's batch). */
  writeStamps(specs: CreateSpec<StampValues>[]): Promise<{ stamps: string[]; tx: string }>;
  /** One live run that counts (board.ts): its checker stamp, created by the stamp's console; with its ghost bytes when `withLog`. */
  getRun(runKey: string, withLog: boolean): Promise<StampedRun | null>;
  /** One live listing that counts (board.ts): its run counts (stamped, held by the stamp's console), and the listing is that console's; with `pay_to` and `hcs`. */
  getListing(listingKey: string): Promise<ListingRow | null>;
  /** One batch from the checker: the run, then its listing (run = the run's predicted key). The smoke script's only. */
  writeRunAndListing(run: CreateSpec<RunValues>, listing: CreateSpec<ListingValues>): Promise<Written>;
  /** The house wallet's address (lowercase): it writes the BOT runs and listings. Null without HOUSE_ARKIV_KEY. */
  readonly house: string | null;
  /**
   * House pairs in ONE transaction from the house wallet: [run1, listing1, run2, listing2, ...],
   * each listing naming its run's predicted key. The caller splits a batch that is refused, then
   * has the checker stamp the runs (house.ts).
   */
  writeHouse(pairs: HousePair[]): Promise<{ runs: string[]; listings: string[]; tx: string }>;
  /** The board of one game and season: the checker's stamps (one page, fastest first) joined to their runs. */
  boardRuns(game: string, season: number): Promise<StampedRun[]>;
  /** The listings of that board: each created by its stamped run's console and naming that run. */
  boardListings(game: string, season: number): Promise<ListingRow[]>;
}

/** The block a date falls in, by the chain's clock (as the SDK resolves `ExpirationTime.atDate`). */
export function blockAtDate(date: Date, t: BlockTiming): bigint {
  const ahead = Math.ceil((date.getTime() / 1000 - t.timeS) / Math.max(1, t.durationS));
  return t.block + BigInt(Math.max(1, ahead));
}

/** The block an expiry resolves to, by the chain's clock now. */
export function expiryBlock(e: ExpirySpec, t: BlockTiming): bigint {
  const d = Math.max(1, t.durationS);
  const blocks = (seconds: number) => BigInt(Math.ceil(seconds / d));
  switch (e.kind) {
    case "atBlock":
      return e.block;
    case "days":
      return t.block + blocks(e.days * 86_400);
    case "hours":
      return t.block + blocks(e.hours * 3_600);
    case "atDate": {
      const at = blockAtDate(e.date, t);
      const least = t.block + blocks(e.atLeastDays * 86_400);
      return at > least ? at : least;
    }
  }
}

/** A read or write that did not complete: Arkiv down, a revert, out of gas, a timeout. */
export class ArkivError extends Error {}

/** A short reason for a log line: no URLs, no access key, nothing key-shaped. */
export function redact(text: string, secrets: readonly string[] = []): string {
  let out = text;
  for (const s of secrets) if (s) out = out.split(s).join("<redacted>");
  // URLs carry the access key; a bare 64-hex run could be a secret. 0x-prefixed entity keys and tx
  // hashes are public and stay (a private key is removed above, by value).
  out = out.replace(/https?:\/\/\S+/g, "<url>").replace(/(?<!0x)\b[0-9a-fA-F]{64}\b/g, "<hex>");
  return out.split("\n")[0].slice(0, 240);
}

export function runFromRow(r: DecodedRow): RunRow {
  const v = r.values;
  return {
    key: r.key,
    creator: r.creator,
    owner: r.owner,
    expiresAt: r.expiresAt,
    game: v.game as string,
    title: v.title as string | undefined,
    season: v.season as number | undefined,
    rules: v.rules as bigint | undefined,
    frames: v.frames as bigint,
    log_h: v.log_h as string,
    runner: v.runner as string,
    book: v.book as string | undefined,
    label: v.label as string | undefined,
    human: v.human as boolean,
    credential: v.credential as string | undefined,
    tool: v.tool as string | undefined,
    log: v.log as Uint8Array | undefined,
    log_enc: v.log_enc as Uint8Array | undefined,
    ...(() => {
      const splits = splitsOf(v);
      return splits ? { splits } : {};
    })(),
  };
}

export function listingFromRow(r: DecodedRow): ListingRow {
  const v = r.values;
  return {
    key: r.key,
    creator: r.creator,
    owner: r.owner,
    expiresAt: r.expiresAt,
    run: v.run as string,
    game: v.game as string,
    season: v.season as number,
    frames: v.frames as bigint,
    log_h: v.log_h as string,
    price: v.price as string,
    seller: v.seller as string,
    ...(typeof v.book === "string" ? { book: v.book } : {}),
    ...(typeof v.label === "string" ? { label: v.label } : {}),
    human: v.human as boolean,
    ...(typeof v.pay_to === "string" ? { pay_to: v.pay_to } : {}),
    ...(typeof v.hcs === "string" ? { hcs: v.hcs } : {}),
  };
}

export function stampFromRow(r: DecodedRow): StampRow {
  const v = r.values;
  const splits = splitsOf(v);
  return {
    key: r.key,
    creator: r.creator,
    expiresAt: r.expiresAt,
    run: v.run as string,
    console: (v.console as string).toLowerCase(),
    game: v.game as string,
    season: v.season as number,
    frames: v.frames as bigint,
    log_h: v.log_h as string,
    ...(typeof v.book === "string" ? { book: v.book } : {}),
    ...(typeof v.label === "string" ? { label: v.label } : {}),
    human: v.human as boolean,
    ...(splits ? { splits } : {}),
    ...(typeof v.final_hash === "bigint" ? { final_hash: v.final_hash } : {}),
    tool: v.tool as string,
  };
}

export function toExpiration(e: ExpirySpec) {
  switch (e.kind) {
    case "atDate":
      return ExpirationTime.atDate(e.date, { atLeast: ExpirationTime.fromDays(e.atLeastDays) });
    case "days":
      return ExpirationTime.fromDays(e.days);
    case "hours":
      return ExpirationTime.fromHours(e.hours);
    case "atBlock":
      return ExpirationTime.atBlock(e.block);
  }
}


export interface SdkArkivOptions {
  /** ARKIV_RPC with the access key already appended (config.arkivRpcUrl). Never logged. */
  rpcUrl: string;
  /** The access key alone, only so error text can be scrubbed of it. */
  accessKey: string;
  /** The checker's private key: stamp reads pin its address, stamps are signed by it. */
  checkerKey?: string;
  /** Pin stamp reads to this checker instead (read-only use, e.g. the snapshot with no key). */
  checkerAddress?: string;
  /** HOUSE_ARKIV_KEY: the house wallet, which writes the BOT runs and listings (never the checker's key). */
  houseKey?: string;
  names?: SchemaNames;
  timeoutMs?: number;
}

/** One game's board as the node answered it: the raw stamp page, and the raw runs and listings of every stamped console. */
export interface BoardPages {
  block: bigint;
  stamps: unknown[];
  runs: unknown[];
  listings: unknown[];
}

export class SdkArkiv implements ArkivPort {
  readonly checker: string | null;
  readonly house: string | null;
  private readonly pub: PublicArkivClient;
  private readonly wallet: WalletArkivClient | null;
  private readonly houseWallet: WalletArkivClient | null;
  private readonly chain: ReturnType<typeof rabdi>;
  private readonly names: SchemaNames;
  private readonly secrets: string[];
  private queue: Promise<unknown> = Promise.resolve();
  private houseQueue: Promise<unknown> = Promise.resolve();

  constructor(private readonly opts: SdkArkivOptions) {
    this.names = opts.names ?? REAL;
    this.chain = rabdi({ accessKey: opts.accessKey });
    const transport = http(opts.rpcUrl, { timeout: opts.timeoutMs ?? 10_000, retryCount: 1 });
    this.pub = createPublicClient({ chain: this.chain, transport, pollingInterval: 1000 }) as unknown as PublicArkivClient;
    this.secrets = [opts.accessKey, encodeURIComponent(opts.accessKey), opts.checkerKey ?? "", opts.houseKey ?? ""].filter(Boolean);
    if (opts.checkerKey) {
      const account = privateKeyToAccount(opts.checkerKey as Hex);
      this.checker = account.address;
      this.wallet = createWalletClient({ chain: this.chain, transport, account, pollingInterval: 1000 }) as unknown as WalletArkivClient;
    } else {
      this.checker = opts.checkerAddress ?? null;
      this.wallet = null;
    }
    if (opts.houseKey) {
      const account = privateKeyToAccount(opts.houseKey as Hex);
      this.house = account.address.toLowerCase();
      this.houseWallet = createWalletClient({ chain: this.chain, transport, account, pollingInterval: 1000 }) as unknown as WalletArkivClient;
    } else {
      this.house = null;
      this.houseWallet = null;
    }
  }

  /** The public client, for scripts (block timing, receipts). */
  get publicClient(): PublicArkivClient {
    return this.pub;
  }

  private fail(err: unknown): ArkivError {
    const e = err as { shortMessage?: string; message?: string; name?: string };
    return new ArkivError(redact(e?.shortMessage ?? e?.message ?? String(err), this.secrets));
  }

  /** One raw arkiv_query call: the reply's data, block and count. */
  async query(query: string, select: RpcSelect, limit = 100): Promise<{ data: unknown[]; blockNumber: bigint; count?: bigint }> {
    try {
      const res = (await this.pub.request({ method: "arkiv_query", params: queryParams(query, select, limit) } as never)) as {
        data: unknown[];
        blockNumber: string;
        count?: string;
      };
      return {
        data: Array.isArray(res?.data) ? res.data : [],
        blockNumber: BigInt(res.blockNumber),
        ...(res.count !== undefined ? { count: BigInt(res.count) } : {}),
      };
    } catch (err) {
      throw this.fail(err);
    }
  }

  async chainId(): Promise<number> {
    try {
      return await this.pub.getChainId();
    } catch (err) {
      throw this.fail(err);
    }
  }

  async balance(address: string): Promise<bigint> {
    try {
      return await this.pub.getBalance({ address: address as Hex });
    } catch (err) {
      throw this.fail(err);
    }
  }

  async blockTiming(): Promise<BlockTiming> {
    try {
      const t = await this.pub.getBlockTiming();
      return { block: t.currentBlock, timeS: Number(t.currentBlockTime), durationS: Number(t.blockDuration) || 2 };
    } catch (err) {
      throw this.fail(err);
    }
  }

  private pinned(): string {
    if (!this.checker) throw new ArkivError("no checker configured");
    return this.checker;
  }

  async runByLogHash(logH: string, owner: string): Promise<RunRow | null> {
    const asked = [...RUN_ALL_ATTRS];
    const res = await this.query(q7RunByLogHash(logH, owner, this.names), selectOf(asked), 1);
    const page = decodePage(res.data, RUN_TYPES, asked, this.names.run, owner);
    return page.rows[0] ? runFromRow(page.rows[0]) : null;
  }

  async liveListingFor(runKey: string, owner: string): Promise<ListingRow | null> {
    const asked = [...LISTING_ATTRS];
    const res = await this.query(qListingForRun(runKey, owner, this.names), selectOf(asked), 1);
    const page = decodePage(res.data, LISTING_TYPES, asked, this.names.listing, owner);
    return page.rows[0] ? listingFromRow(page.rows[0]) : null;
  }

  async stampByLogHash(logH: string): Promise<StampRow | null> {
    const asked = [...STAMP_ATTRS];
    const res = await this.query(qStampByLogHash(logH, this.pinned(), this.names), selectOf(asked), 1);
    const page = decodePage(res.data, STAMP_TYPES, asked, this.names.stamp, this.pinned());
    return page.rows[0] ? stampFromRow(page.rows[0]) : null;
  }

  /** The checker's stamp of one run, or null. */
  async stampForRun(runKey: string): Promise<StampRow | null> {
    const asked = [...STAMP_ATTRS];
    const res = await this.query(qStampForRun(runKey, this.pinned(), this.names), selectOf(asked), 1);
    const page = decodePage(res.data, STAMP_TYPES, asked, this.names.stamp, this.pinned());
    return page.rows[0] ? stampFromRow(page.rows[0]) : null;
  }

  /**
   * `arkiv_getEntity`, decoded by the SDK's own getEntity (each attribute typed by the tag the node
   * gives it). One request: the raw reply is also looked at for a payload or a content type, which
   * the SDK's entity leaves out.
   */
  async getEntity(entityKey: string): Promise<EntityRow | null> {
    let raw: Record<string, unknown> | null;
    let e: Record<string, unknown>;
    try {
      raw = (await this.pub.request({ method: "arkiv_getEntity", params: [keyValue(entityKey as Hex).value] } as never)) as Record<string, unknown> | null;
      if (raw === null || typeof raw !== "object") return null;
      const answered = raw;
      const local = createPublicClient({ chain: this.chain, transport: custom({ request: async () => answered }) }) as unknown as PublicArkivClient;
      e = (await local.getEntity(entityKey as Hex)) as unknown as Record<string, unknown>;
    } catch (err) {
      if (err instanceof NoEntityFoundError) return null;
      throw this.fail(err);
    }
    const attrs = { ...((e.$attributes ?? {}) as Record<string, TypedValue>) };
    const tag = attrs[SCHEMA_ATTR];
    delete attrs[SCHEMA_ATTR];
    const flags = e.$creationFlags as { readonly?: boolean; permissionlessExtension?: boolean } | undefined;
    const lower = (v: unknown) => (typeof v === "string" ? v.toLowerCase() : null);
    const carries = (v: unknown) => v !== undefined && v !== null && v !== "" && v !== "0x";
    return {
      key: (lower(e.$key) ?? entityKey).toLowerCase(),
      creator: lower(e.$creator),
      owner: lower(e.$owner),
      expiresAt: typeof e.$expiresAt === "bigint" ? e.$expiresAt : null,
      flags: flags && typeof flags.readonly === "boolean" && typeof flags.permissionlessExtension === "boolean" ? { readonly: flags.readonly, permissionlessExtension: flags.permissionlessExtension } : null,
      schema: tag?.type === "str" && typeof tag.value === "string" ? tag.value : null,
      values: attrs,
      payload: carries(raw.payload) || carries(raw.contentType) || carries(raw.content_type),
    };
  }

  writeStamp(spec: CreateSpec<StampValues>): Promise<{ stamp: string; tx: string }> {
    return this.writeStamps([spec]).then((w) => ({ stamp: w.stamps[0], tx: w.tx }));
  }

  writeStamps(specs: CreateSpec<StampValues>[]): Promise<{ stamps: string[]; tx: string }> {
    return this.serial(async () => {
      const wallet = this.needWallet();
      try {
        const res = await wallet.executeBatch({
          creates: specs.map((spec) => ({
            schema: this.schemas().stamp,
            values: toSdkValues("stamp", spec.values as unknown as Record<string, unknown>) as never,
            expiration: toExpiration(spec.expiry),
            flags: spec.flags,
          })),
        } as never);
        return { stamps: res.createdEntities.map((k) => k.toLowerCase()), tx: res.txHash };
      } catch (err) {
        throw err instanceof ArkivError ? err : this.fail(err);
      }
    });
  }

  async getRun(runKey: string, withLog: boolean): Promise<StampedRun | null> {
    const st = await this.stampForRun(runKey);
    if (!st || !WALLET_RE.test(st.console)) return null;
    const asked = withLog ? [...RUN_ALL_ATTRS, "log", "log_enc"] : [...RUN_ALL_ATTRS];
    const res = await this.query(q6Run(runKey, st.console, this.names), selectOf(asked, { owner: true }), 1);
    const page = decodePage(res.data, RUN_TYPES, asked, this.names.run, st.console);
    const r = page.rows[0] ? runFromRow(page.rows[0]) : null;
    return r && runMismatch(st, r) === null ? stamped(st, r) : null;
  }

  async getListing(listingKey: string): Promise<ListingRow | null> {
    const asked = [...LISTING_ATTRS];
    const res = await this.query(q6ListingByKey(listingKey, this.names), selectOf(asked, { owner: true }), 1);
    const page = decodePage(res.data, LISTING_TYPES, asked, this.names.listing, null);
    const l = page.rows[0] ? listingFromRow(page.rows[0]) : null;
    if (!l) return null;
    // The listing counts only for a run that counts: its stamp, then the run as its console holds it.
    const st = await this.stampForRun(l.run);
    if (!st || !WALLET_RE.test(st.console) || listingMismatch(st, l) !== null) return null;
    const runAsked = [...RUN_ALL_ATTRS];
    const runRes = await this.query(q6Run(l.run, st.console, this.names), selectOf(runAsked, { owner: true }), 1);
    const runPage = decodePage(runRes.data, RUN_TYPES, runAsked, this.names.run, st.console);
    const r = runPage.rows[0] ? runFromRow(runPage.rows[0]) : null;
    return r && runMismatch(st, r) === null ? l : null;
  }

  /**
   * One game's board, raw: the checker's stamps (one page, fastest first), then the runs and the
   * listings of every console those stamps name (Q1 and Q2 pinned to that wallet). The snapshot
   * keeps these pages; boardRuns and boardListings join them.
   */
  async boardPages(game: string, season: number, want: { runs?: boolean; listings?: boolean } = { runs: true, listings: true }): Promise<BoardPages> {
    const asked = [...STAMP_ATTRS];
    const res = await this.query(q1Stamps(game, season, this.pinned(), this.names), selectOf(asked), PAGE);
    const stamps = decodePage(res.data, STAMP_TYPES, asked, this.names.stamp, this.pinned()).rows.map(stampFromRow);
    const consoles = [...new Set(stamps.map((s) => s.console))].filter((w) => WALLET_RE.test(w));
    const pages = await Promise.all(
      consoles.map(async (w) => ({
        runs: want.runs ? (await this.query(q1Board(game, season, w, this.names), selectOf(RUN_BOARD_ATTRS, { owner: true }), PAGE)).data : [],
        listings: want.listings ? (await this.query(q2Listings(game, season, w, this.names), selectOf(LISTING_ATTRS, { owner: true }), PAGE)).data : [],
      })),
    );
    return { block: res.blockNumber, stamps: res.data, runs: pages.flatMap((p) => p.runs), listings: pages.flatMap((p) => p.listings) };
  }

  /** The raw pages decoded (stamps pinned to the checker; runs and listings checked against the stamps) and joined. */
  joinPages(p: BoardPages): ReturnType<typeof joinBoard> {
    const stamps = decodePage(p.stamps, STAMP_TYPES, STAMP_ATTRS, this.names.stamp, this.pinned()).rows.map(stampFromRow);
    const runs = decodePage(p.runs, RUN_TYPES, RUN_BOARD_ATTRS, this.names.run, null).rows.map(runFromRow);
    const listings = decodePage(p.listings, LISTING_TYPES, LISTING_ATTRS, this.names.listing, null).rows.map(listingFromRow);
    return joinBoard(stamps, runs, listings);
  }

  async boardRuns(game: string, season: number): Promise<StampedRun[]> {
    return this.joinPages(await this.boardPages(game, season, { runs: true })).runs;
  }

  async boardListings(game: string, season: number): Promise<ListingRow[]> {
    return this.joinPages(await this.boardPages(game, season, { runs: true, listings: true })).listings;
  }

  /** The checker's writes, one at a time: one wallet, one entity nonce. */
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.queue.then(fn, fn);
    this.queue = run.catch(() => undefined);
    return run;
  }

  /** The house wallet's writes, one at a time, on their own queue (their own nonce). */
  private houseSerial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.houseQueue.then(fn, fn);
    this.houseQueue = run.catch(() => undefined);
    return run;
  }

  private schemas() {
    return this.names === REAL || this.names.run === REAL.run ? { run: Run, listing: Listing, stamp: Stamp } : { run: SmokeRun, listing: SmokeListing, stamp: SmokeStamp };
  }

  private needWallet(): WalletArkivClient {
    if (!this.wallet || !this.checker) throw new ArkivError("no checker key configured");
    return this.wallet;
  }

  writeRunAndListing(run: CreateSpec<RunValues>, listing: CreateSpec<ListingValues>): Promise<Written> {
    return this.serial(async () => {
      const wallet = this.needWallet();
      const s = this.schemas();
      try {
        const [r, l] = await this.pub.predictEntityKeys({ owner: this.checker as Hex, count: 2 });
        const res = await wallet.executeBatch({
          creates: [
            {
              schema: s.run,
              values: toSdkValues("run", run.values as unknown as Record<string, unknown>) as never,
              expiration: toExpiration(run.expiry),
              flags: run.flags,
              salt: r.salt,
            },
            {
              schema: s.listing,
              values: toSdkValues("listing", { ...listing.values, run: r.key }) as never,
              expiration: toExpiration(listing.expiry),
              flags: listing.flags,
              salt: l.salt,
            },
          ],
        } as never);
        const [runKey, listingKey] = res.createdEntities.map((k) => k.toLowerCase());
        if (runKey !== r.key.toLowerCase() || listingKey !== l.key.toLowerCase()) {
          // Another writer used the checker's nonce in between: the listing names a key that moved.
          throw new ArkivError("the predicted keys moved (another writer used the checker wallet)");
        }
        return { run: runKey, listing: listingKey, tx: res.txHash };
      } catch (err) {
        throw err instanceof ArkivError ? err : this.fail(err);
      }
    });
  }

  writeHouse(pairs: HousePair[]): Promise<{ runs: string[]; listings: string[]; tx: string }> {
    return this.houseSerial(async () => {
      const wallet = this.houseWallet;
      if (!wallet || !this.house) throw new ArkivError("no house key configured (HOUSE_ARKIV_KEY)");
      const s = this.schemas();
      try {
        const keys = await this.pub.predictEntityKeys({ owner: this.house as Hex, count: 2 * pairs.length });
        const creates = pairs.flatMap((p, i) => {
          const r = keys[2 * i];
          const l = keys[2 * i + 1];
          return [
            {
              schema: s.run,
              values: toSdkValues("run", p.run.values as unknown as Record<string, unknown>) as never,
              expiration: toExpiration(p.run.expiry),
              flags: p.run.flags,
              salt: r.salt,
            },
            {
              schema: s.listing,
              values: toSdkValues("listing", { ...p.listing.values, run: r.key }) as never,
              expiration: toExpiration(p.listing.expiry),
              flags: p.listing.flags,
              salt: l.salt,
            },
          ];
        });
        const res = await wallet.executeBatch({ creates } as never);
        const made = res.createdEntities.map((k) => k.toLowerCase());
        if (made.length !== keys.length || made.some((k, i) => k !== keys[i].key.toLowerCase())) {
          throw new ArkivError("the predicted keys moved (another writer used the house wallet)");
        }
        return { runs: made.filter((_, i) => i % 2 === 0), listings: made.filter((_, i) => i % 2 === 1), tx: res.txHash };
      } catch (err) {
        throw err instanceof ArkivError ? err : this.fail(err);
      }
    });
  }

  /**
   * A run alone, signed by this port's own key (not part of ArkivPort): the look-alike demo builds a
   * port on the STRANGER key to show that a run nobody stamped never reaches a board.
   */
  writeRun(run: CreateSpec<RunValues>): Promise<{ run: string; tx: string }> {
    return this.serial(async () => {
      const wallet = this.needWallet();
      try {
        const res = await wallet.executeBatch({
          creates: [
            {
              schema: this.schemas().run,
              values: toSdkValues("run", run.values as unknown as Record<string, unknown>) as never,
              expiration: toExpiration(run.expiry),
              flags: run.flags,
            },
          ],
        } as never);
        return { run: res.createdEntities[0].toLowerCase(), tx: res.txHash };
      } catch (err) {
        throw this.fail(err);
      }
    });
  }
}
