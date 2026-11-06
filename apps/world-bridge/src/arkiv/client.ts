/**
 * ArkivPort: everything the service asks of Arkiv, behind one interface so the publish pipeline is
 * tested against a fake (test/fake-arkiv.ts) and runs live on the SDK.
 *
 * The real implementation (SdkArkiv) uses @arkiv-network/sdk 1.0.1 on Rabdi:
 * - reads are the exact Q-strings of queries.ts over `arkiv_query`, each row validated like every
 *   other raw reader (rows.ts), pinned to the checker;
 * - writes go through the SDK's typed schemas (schema.ts), signed by the checker, on one serial
 *   queue: one wallet, one entity nonce, so a batch's predicted keys hold;
 * - the access key rides in the RPC URL's last path segment and never reaches a log line: every
 *   error is reduced to a short reason with the key and anything key-shaped removed.
 *
 * Console-owned records (spec: the console owns its records): a player's run and listing are
 * written by the console's own wallet, never here. The checker writes the stamp (`writeStamp`) once
 * `getEntity` read the console's entities back and they were exactly what publish issued.
 * `writeRunAndListing` and `writeListing` are the checker-signed paths from before; publish no
 * longer calls them.
 */
import {
  createPublicClient,
  createWalletClient,
  ExpirationTime,
  NoEntityFoundError,
  type PublicArkivClient,
  type WalletArkivClient,
} from "@arkiv-network/sdk";
import { rabdi } from "@arkiv-network/sdk/chains";
import { http, type Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import {
  queryParams,
  qListingForRun,
  q1Board,
  q2Listings,
  q6Listing,
  q6Run,
  q7RunByLogHash,
  qStampByLogHash,
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

export interface RunRow {
  key: string;
  creator: string | null;
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

export interface ListingRow {
  key: string;
  creator: string | null;
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
  /** Q7: the live run with this log, if any, created by `owner` (default: the checker). */
  runByLogHash(logH: string, owner?: string): Promise<RunRow | null>;
  /** The live listing of this run, if any, created by `owner` (default: the checker). */
  liveListingFor(runKey: string, owner?: string): Promise<ListingRow | null>;
  /** Q7 on stamps: the checker's live stamp of the run with this log, if any. */
  stampByLogHash(logH: string): Promise<StampRow | null>;
  /** One live entity by key, whoever created it (null: none, deleted or expired). */
  getEntity(key: string): Promise<EntityRow | null>;
  /** One stamp, signed by the checker. */
  writeStamp(spec: CreateSpec<StampValues>): Promise<{ stamp: string; tx: string }>;
  /** Q6 on runs: one live run the checker wrote, with its ghost bytes when `withLog`. */
  getRun(runKey: string, withLog: boolean): Promise<RunRow | null>;
  /** Q6 on listings: one live listing the checker wrote, with `pay_to` and `hcs`. */
  getListing(listingKey: string): Promise<ListingRow | null>;
  /** One batch: the run, then its listing (run = the run's predicted key). The smoke script's only. */
  writeRunAndListing(run: CreateSpec<RunValues>, listing: CreateSpec<ListingValues>): Promise<Written>;
  /**
   * A listing for a run already on Arkiv. With `replaces`, the same batch deletes that (older) live
   * listing of the run, so a relist leaves one listing per run.
   */
  writeListing(runKey: string, listing: CreateSpec<ListingValues>, replaces?: string): Promise<{ listing: string; tx: string }>;
  /** A run alone (the open tier). */
  writeRun(run: CreateSpec<RunValues>): Promise<{ run: string; tx: string }>;
  /**
   * House pairs in ONE transaction: [run1, listing1, run2, listing2, ...], each listing naming its
   * run's predicted key. The caller splits a batch that is refused (house.ts).
   */
  writeHouse(pairs: HousePair[]): Promise<{ runs: string[]; listings: string[]; tx: string }>;
  /** Q1: the run board of one game and season (one page, fastest first), with splits and labels. */
  boardRuns(game: string, season: number): Promise<RunRow[]>;
  /** Q2: the live listings of one game and season (one page, fastest first). */
  boardListings(game: string, season: number): Promise<ListingRow[]>;
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
  /** The checker's private key: reads pin its address, writes are signed by it. */
  checkerKey?: string;
  /** Pin reads to this creator instead (read-only use, e.g. the snapshot with no key). */
  checkerAddress?: string;
  names?: SchemaNames;
  timeoutMs?: number;
}

export class SdkArkiv implements ArkivPort {
  readonly checker: string | null;
  private readonly pub: PublicArkivClient;
  private readonly wallet: WalletArkivClient | null;
  private readonly names: SchemaNames;
  private readonly secrets: string[];
  private queue: Promise<unknown> = Promise.resolve();

  constructor(private readonly opts: SdkArkivOptions) {
    this.names = opts.names ?? REAL;
    const chain = rabdi({ accessKey: opts.accessKey });
    const transport = http(opts.rpcUrl, { timeout: opts.timeoutMs ?? 10_000, retryCount: 1 });
    this.pub = createPublicClient({ chain, transport, pollingInterval: 1000 }) as unknown as PublicArkivClient;
    this.secrets = [opts.accessKey, encodeURIComponent(opts.accessKey), opts.checkerKey ?? ""].filter(Boolean);
    if (opts.checkerKey) {
      const account = privateKeyToAccount(opts.checkerKey as Hex);
      this.checker = account.address;
      this.wallet = createWalletClient({ chain, transport, account, pollingInterval: 1000 }) as unknown as WalletArkivClient;
    } else {
      this.checker = opts.checkerAddress ?? null;
      this.wallet = null;
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

  private pinned(): string {
    if (!this.checker) throw new ArkivError("no checker configured");
    return this.checker;
  }

  async runByLogHash(logH: string, owner?: string): Promise<RunRow | null> {
    const by = owner ?? this.pinned();
    const asked = [...RUN_ALL_ATTRS];
    const res = await this.query(q7RunByLogHash(logH, by, this.names), selectOf(asked), 1);
    const page = decodePage(res.data, RUN_TYPES, asked, this.names.run, by);
    return page.rows[0] ? runFromRow(page.rows[0]) : null;
  }

  async liveListingFor(runKey: string, owner?: string): Promise<ListingRow | null> {
    const by = owner ?? this.pinned();
    const asked = [...LISTING_ATTRS];
    const res = await this.query(qListingForRun(runKey, by, this.names), selectOf(asked), 1);
    const page = decodePage(res.data, LISTING_TYPES, asked, this.names.listing, by);
    return page.rows[0] ? listingFromRow(page.rows[0]) : null;
  }

  async stampByLogHash(logH: string): Promise<StampRow | null> {
    const asked = [...STAMP_ATTRS];
    const res = await this.query(qStampByLogHash(logH, this.pinned(), this.names), selectOf(asked), 1);
    const page = decodePage(res.data, STAMP_TYPES, asked, this.names.stamp, this.pinned());
    return page.rows[0] ? stampFromRow(page.rows[0]) : null;
  }

  /** `arkiv_getEntity` through the SDK, which types each attribute by the tag the node gives it. */
  async getEntity(entityKey: string): Promise<EntityRow | null> {
    let e: Record<string, unknown>;
    try {
      e = (await this.pub.getEntity(entityKey as Hex)) as unknown as Record<string, unknown>;
    } catch (err) {
      if (err instanceof NoEntityFoundError) return null;
      throw this.fail(err);
    }
    const attrs = { ...((e.$attributes ?? {}) as Record<string, TypedValue>) };
    const tag = attrs[SCHEMA_ATTR];
    delete attrs[SCHEMA_ATTR];
    const flags = e.$creationFlags as { readonly?: boolean; permissionlessExtension?: boolean } | undefined;
    const lower = (v: unknown) => (typeof v === "string" ? v.toLowerCase() : null);
    return {
      key: (lower(e.$key) ?? entityKey).toLowerCase(),
      creator: lower(e.$creator),
      owner: lower(e.$owner),
      expiresAt: typeof e.$expiresAt === "bigint" ? e.$expiresAt : null,
      flags: flags && typeof flags.readonly === "boolean" && typeof flags.permissionlessExtension === "boolean" ? { readonly: flags.readonly, permissionlessExtension: flags.permissionlessExtension } : null,
      schema: tag?.type === "str" && typeof tag.value === "string" ? tag.value : null,
      values: attrs,
    };
  }

  writeStamp(spec: CreateSpec<StampValues>): Promise<{ stamp: string; tx: string }> {
    return this.serial(async () => {
      const wallet = this.needWallet();
      try {
        const res = await wallet.executeBatch({
          creates: [
            {
              schema: this.schemas().stamp,
              values: toSdkValues("stamp", spec.values as unknown as Record<string, unknown>) as never,
              expiration: toExpiration(spec.expiry),
              flags: spec.flags,
            },
          ],
        } as never);
        return { stamp: res.createdEntities[0].toLowerCase(), tx: res.txHash };
      } catch (err) {
        throw err instanceof ArkivError ? err : this.fail(err);
      }
    });
  }

  async getRun(runKey: string, withLog: boolean): Promise<RunRow | null> {
    const asked = withLog ? [...RUN_ALL_ATTRS, "log", "log_enc"] : [...RUN_ALL_ATTRS];
    const res = await this.query(q6Run(runKey, this.pinned(), this.names), selectOf(asked), 1);
    const page = decodePage(res.data, RUN_TYPES, asked, this.names.run, this.pinned());
    return page.rows[0] ? runFromRow(page.rows[0]) : null;
  }

  async getListing(listingKey: string): Promise<ListingRow | null> {
    const asked = [...LISTING_ATTRS];
    const res = await this.query(q6Listing(listingKey, this.pinned(), this.names), selectOf(asked), 1);
    const page = decodePage(res.data, LISTING_TYPES, asked, this.names.listing, this.pinned());
    return page.rows[0] ? listingFromRow(page.rows[0]) : null;
  }

  /** Writes run one at a time: one wallet, one entity nonce. */
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.queue.then(fn, fn);
    this.queue = run.catch(() => undefined);
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

  writeListing(runKey: string, listing: CreateSpec<ListingValues>, replaces?: string): Promise<{ listing: string; tx: string }> {
    return this.serial(async () => {
      const wallet = this.needWallet();
      try {
        const res = await wallet.executeBatch({
          creates: [
            {
              schema: this.schemas().listing,
              values: toSdkValues("listing", { ...listing.values, run: runKey }) as never,
              expiration: toExpiration(listing.expiry),
              flags: listing.flags,
            },
          ],
          ...(replaces ? { deletes: [{ entityKey: replaces as Hex }] } : {}),
        } as never);
        return { listing: res.createdEntities[0].toLowerCase(), tx: res.txHash };
      } catch (err) {
        throw this.fail(err);
      }
    });
  }

  async boardRuns(game: string, season: number): Promise<RunRow[]> {
    const asked = [...RUN_BOARD_ATTRS];
    const res = await this.query(q1Board(game, season, this.pinned(), this.names), selectOf(asked), 100);
    return decodePage(res.data, RUN_TYPES, asked, this.names.run, this.pinned()).rows.map(runFromRow);
  }

  async boardListings(game: string, season: number): Promise<ListingRow[]> {
    const asked = [...LISTING_ATTRS];
    const res = await this.query(q2Listings(game, season, this.pinned(), this.names), selectOf(asked), 100);
    return decodePage(res.data, LISTING_TYPES, asked, this.names.listing, this.pinned()).rows.map(listingFromRow);
  }

  writeHouse(pairs: HousePair[]): Promise<{ runs: string[]; listings: string[]; tx: string }> {
    return this.serial(async () => {
      const wallet = this.needWallet();
      const s = this.schemas();
      try {
        const keys = await this.pub.predictEntityKeys({ owner: this.checker as Hex, count: 2 * pairs.length });
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
          throw new ArkivError("the predicted keys moved (another writer used the checker wallet)");
        }
        return { runs: made.filter((_, i) => i % 2 === 0), listings: made.filter((_, i) => i % 2 === 1), tx: res.txHash };
      } catch (err) {
        throw err instanceof ArkivError ? err : this.fail(err);
      }
    });
  }

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
