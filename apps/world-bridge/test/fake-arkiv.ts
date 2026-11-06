/**
 * An in-memory Arkiv behind the ArkivPort interface, and a scripted checker, for the publish and
 * ghost tests. Rows are kept with the values, flags and expiry they were written with, so tests can
 * assert every column. Nothing here touches the network.
 *
 * Console-owned records, as on the chain: runs and listings are created by a console's wallet (or
 * the house wallet), stamps by the CHECKER. The readers (boardRuns, boardListings, getRun,
 * getListing) go through the same join as the real port (src/arkiv/board.ts): a run counts only
 * when a checker stamp names it and its creator is the stamp's console.
 *
 * - `addRun` puts a run on the board as a console that published it would: created by WALLET_A
 *   (or the given wallet) and stamped by the checker. `{stamp: false}` leaves it unstamped (a
 *   look-alike, an old row). `stampRun` stamps a run later, with any copied column changed.
 * - The console's half of a publish lives here too: `consoleWrite` writes what a sign stage issued
 *   from a console's wallet (as the launcher's signer would), `linkWallet` binds a console with an
 *   approved wallet to a book (as an approved link leaves it), and `consoleFinish` drives a job
 *   through sign -> written -> done.
 */
import { createHash, randomBytes } from "node:crypto";
import { joinBoard, listingMismatch, runMismatch, stamped } from "../src/arkiv/board.js";
import type {
  ArkivPort,
  BlockTiming,
  CreateSpec,
  EntityRow,
  HousePair,
  ListingRow,
  ListingValues,
  RunRow,
  RunValues,
  StampedRun,
  StampRow,
  StampValues,
  TypedValue,
} from "../src/arkiv/client.js";
import { ArkivError, expiryBlock, stampValues } from "../src/arkiv/client.js";
import type { Publisher, PublishView } from "../src/arkiv/publish.js";
import { splitsOf } from "../src/arkiv/rows.js";
import { LISTING_SCHEMA, RUN_SCHEMA, STAMP_FLAGS, STAMP_SCHEMA, toSdkValues } from "../src/arkiv/schema.js";
import { fromSpecJson } from "../src/arkiv/spec-json.js";
import { CheckerError, type CheckerPort, type ReplayResult } from "../src/arkiv/checker.js";
import type { Store } from "../src/store.js";
import { waitFor } from "./helpers.js";

export const CHECKER = "0x1111111111111111111111111111111111111111";
export const STRANGER = "0x2222222222222222222222222222222222222222";
/** Two console wallets (lowercase, as the bridge keeps them). */
export const WALLET_A = `0x${"a1".repeat(20)}`;
export const WALLET_B = `0x${"b2".repeat(20)}`;
/** The house wallet (HOUSE_ARKIV_KEY's address): it creates the BOT runs and listings. */
export const HOUSE_WALLET = `0x${"c3".repeat(20)}`;

export interface StoredRun {
  key: string;
  creator: string;
  spec: CreateSpec<RunValues>;
  live: boolean;
  /** Who owns it now, when not its creator (ownership moved). */
  owner?: string;
}
export interface StoredListing {
  key: string;
  creator: string;
  run: string;
  spec: CreateSpec<ListingValues>;
  live: boolean;
  owner?: string;
}
export interface StoredStamp {
  key: string;
  creator: string;
  spec: CreateSpec<StampValues>;
  live: boolean;
}

/** What a sign stage issues (publish.ts), as the console receives it. */
export interface Issue {
  chain_id: number;
  rpc: string;
  run: unknown;
  run_key: string | null;
  listing: unknown;
  replaces: string | null;
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

let counter = 0;
function newKey(): string {
  counter += 1;
  return `0x${createHash("sha256").update(`key-${counter}`).digest("hex")}`;
}

const bigSplits = (v: { frames: number; s1?: number; s2?: number; s3?: number; s4?: number; split_kind?: string }) =>
  splitsOf({
    frames: BigInt(v.frames),
    ...(v.s1 !== undefined ? { s1: BigInt(v.s1) } : {}),
    ...(v.s2 !== undefined ? { s2: BigInt(v.s2) } : {}),
    ...(v.s3 !== undefined ? { s3: BigInt(v.s3) } : {}),
    ...(v.s4 !== undefined ? { s4: BigInt(v.s4) } : {}),
    ...(v.split_kind !== undefined ? { split_kind: v.split_kind } : {}),
  });

export class FakeArkiv implements ArkivPort {
  runs: StoredRun[] = [];
  listings: StoredListing[] = [];
  stamps: StoredStamp[] = [];
  /** The bridge's transactions: the checker's (stamps, the smoke's run+listing) and the house wallet's. */
  batches: { kind: "run+listing" | "house" | "stamp"; tx: string; creates?: number; creator?: string }[] = [];
  /** Transactions a console's wallet signed (consoleWrite). */
  consoleTxs: { tx: string; creator: string; creates: number; deletes: number }[] = [];
  /** The house wallet (null: no HOUSE_ARKIV_KEY). */
  house: string | null = HOUSE_WALLET;
  /** The chain's clock: block 1,000,000 at 1.8e9 s (the publish tests' T0), 2 s blocks. */
  timing: BlockTiming = { block: 1_000_000n, timeS: 1_800_000_000, durationS: 2 };
  /** An entity's expiry block, when not the one its expiry spec resolves to by `timing`. */
  expiresAt = new Map<string, bigint>();
  /** getEntity answers these fields instead, by key (a node that leaves out $owner or the flags). */
  entityEdit = new Map<string, Partial<EntityRow>>();
  /** Entities that carry a payload or a content type (getEntity says so). */
  payloadOn = new Set<string>();
  /** getEntity answers null for this many more calls (a node that has not seen the block yet). */
  lagEntityReads = 0;
  /** stampByLogHash answers null for this many more calls (a stamp the node does not show yet). */
  lagStampReads = 0;
  /** A transaction with more creates than this is refused (gas or size), as Arkiv would. */
  maxCreates = Infinity;
  chain = 7794095;
  balances = new Map<string, bigint>([[CHECKER.toLowerCase(), 10n ** 18n]]);
  /** Throw on the next n writes (Arkiv down, a revert). */
  failWrites = 0;
  /** The next n stamp writes land and then throw (the receipt never came back). */
  failAfterLanding = 0;
  /** Throw on every read. */
  readsDown = false;
  /** Hold every write until released. */
  holdWrites: Promise<void> | null = null;

  async chainId(): Promise<number> {
    if (this.readsDown) throw new ArkivError("down");
    return this.chain;
  }

  async balance(address: string): Promise<bigint> {
    if (this.readsDown) throw new ArkivError("down");
    return this.balances.get(address.toLowerCase()) ?? 0n;
  }

  async blockTiming(): Promise<BlockTiming> {
    if (this.readsDown) throw new ArkivError("down");
    return { ...this.timing };
  }

  private expiryOf(key: string, spec: CreateSpec<object>): bigint {
    return this.expiresAt.get(key) ?? expiryBlock(spec.expiry, this.timing);
  }

  /**
   * A run as a console that published it leaves it: created by `creator` (WALLET_A) and, unless
   * `stamp` is false, stamped by the checker (console = its creator, the columns copied).
   */
  addRun(values: RunValues, creator = WALLET_A, opts: { stamp?: boolean } = {}): string {
    const key = newKey();
    this.runs.push({ key, creator: creator.toLowerCase(), live: true, spec: { values, flags: { readonly: true, permissionlessExtension: true }, expiry: { kind: "days", days: 30 } } });
    if (opts.stamp !== false) this.stampRun(key);
    return key;
  }

  /** The checker's stamp of a run here, its columns copied (`over` changes any of them). */
  stampRun(runKey: string, over: Partial<StampValues> = {}): string {
    const r = this.runs.find((x) => x.key === runKey.toLowerCase());
    if (!r) throw new Error(`no run ${runKey}`);
    const key = newKey();
    this.stamps.push({
      key,
      creator: CHECKER,
      live: true,
      spec: { values: { ...stampValues(r.spec.values, r.key, r.creator, null, r.spec.values.tool), ...over }, flags: { ...STAMP_FLAGS }, expiry: r.spec.expiry },
    });
    return key;
  }

  private runRow(r: StoredRun, withLog: boolean): RunRow {
    const v = r.spec.values;
    const splits = bigSplits(v);
    return {
      key: r.key,
      creator: r.creator,
      expiresAt: this.expiryOf(r.key, r.spec),
      game: v.game,
      title: v.title,
      season: v.season,
      rules: BigInt(v.rules),
      frames: BigInt(v.frames),
      log_h: v.log_h,
      runner: v.runner,
      book: v.book,
      label: v.label,
      human: v.human,
      credential: v.credential,
      tool: v.tool,
      ...(withLog ? { log: v.log, log_enc: v.log_enc } : {}),
      ...(splits ? { splits } : {}),
    };
  }

  private stampRow(s: StoredStamp): StampRow {
    const v = s.spec.values;
    const splits = bigSplits(v);
    return {
      key: s.key,
      creator: s.creator,
      expiresAt: this.expiryOf(s.key, s.spec),
      run: v.run,
      console: v.console,
      game: v.game,
      season: v.season,
      frames: BigInt(v.frames),
      log_h: v.log_h,
      ...(v.book !== undefined ? { book: v.book } : {}),
      ...(v.label !== undefined ? { label: v.label } : {}),
      human: v.human,
      ...(splits ? { splits } : {}),
      ...(v.final_hash !== undefined ? { final_hash: BigInt(v.final_hash) } : {}),
      tool: v.tool,
    };
  }

  private liveStamps(): StoredStamp[] {
    return this.stamps.filter((s) => s.live && same(s.creator, CHECKER));
  }

  async runByLogHash(logH: string, owner: string): Promise<RunRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const r = this.runs.find((x) => x.live && same(x.creator, owner) && x.spec.values.log_h === logH);
    return r ? this.runRow(r, false) : null;
  }

  async stampByLogHash(logH: string): Promise<StampRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    if (this.lagStampReads > 0) {
      this.lagStampReads -= 1;
      return null;
    }
    const s = this.liveStamps().find((x) => x.spec.values.log_h === logH);
    return s ? this.stampRow(s) : null;
  }

  /** Every live entity by key, whoever created it, typed as the SDK reads it back. */
  async getEntity(key: string): Promise<EntityRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    if (this.lagEntityReads > 0) {
      this.lagEntityReads -= 1;
      return null;
    }
    const k = key.toLowerCase();
    const row = (kind: "run" | "listing" | "stamp", e: { key: string; creator: string; owner?: string; spec: CreateSpec<object> }, extra: Record<string, unknown> = {}): EntityRow => ({
      key: e.key,
      creator: e.creator.toLowerCase(),
      owner: (e.owner ?? e.creator).toLowerCase(),
      expiresAt: this.expiryOf(e.key, e.spec),
      flags: { ...e.spec.flags },
      schema: kind === "run" ? RUN_SCHEMA : kind === "listing" ? LISTING_SCHEMA : STAMP_SCHEMA,
      values: toSdkValues(kind, { ...(e.spec.values as Record<string, unknown>), ...extra }) as Record<string, TypedValue>,
      payload: this.payloadOn.has(e.key),
      ...(this.entityEdit.get(e.key) ?? {}),
    });
    const r = this.runs.find((x) => x.live && x.key === k);
    if (r) return row("run", r);
    const l = this.listings.find((x) => x.live && x.key === k);
    if (l) return row("listing", l, { run: l.run });
    const s = this.stamps.find((x) => x.live && x.key === k);
    return s ? row("stamp", s) : null;
  }

  async writeStamp(spec: CreateSpec<StampValues>) {
    const w = await this.writeStamps([spec]);
    return { stamp: w.stamps[0], tx: w.tx };
  }

  async writeStamps(specs: CreateSpec<StampValues>[]) {
    await this.gate();
    if (specs.length > this.maxCreates) throw new ArkivError("exceeds the block gas limit");
    const stamps = specs.map((spec) => {
      const key = newKey();
      this.stamps.push({ key, creator: CHECKER, spec, live: true });
      return key;
    });
    const tx = newKey();
    this.batches.push({ kind: "stamp", tx, creates: specs.length, creator: CHECKER });
    if (this.failAfterLanding > 0) {
      this.failAfterLanding -= 1;
      throw new ArkivError("timed out while waiting for the transaction receipt");
    }
    return { stamps, tx };
  }

  /**
   * The console's signer: write what a sign stage issued, in one transaction from `wallet` (the
   * run, then its listing naming the run; or, for a relist, the listing alone for the stamped run,
   * deleting the one it replaces unless `keepReplaced`). `edit` changes the values before they go
   * out (a console that writes something else).
   */
  consoleWrite(
    wallet: string,
    issue: Issue,
    edit: { run?: (v: Record<string, unknown>) => void; listing?: (v: Record<string, unknown>) => void; keepReplaced?: boolean } = {},
  ): { tx: string; run: string; listing: string } {
    const creator = wallet.toLowerCase();
    let runKey: string;
    if (issue.run !== null) {
      const spec = fromSpecJson<RunValues>(issue.run);
      edit.run?.(spec.values as unknown as Record<string, unknown>);
      runKey = newKey();
      this.runs.push({ key: runKey, creator, spec, live: true });
    } else {
      runKey = String(issue.run_key);
    }
    const lspec = fromSpecJson<ListingValues>(issue.listing);
    edit.listing?.(lspec.values as unknown as Record<string, unknown>);
    const listingKey = newKey();
    this.listings.push({ key: listingKey, creator, run: runKey, spec: lspec, live: true });
    if (issue.replaces && !edit.keepReplaced) {
      const old = this.listings.find((x) => x.key === issue.replaces && same(x.creator, creator));
      if (old) old.live = false;
    }
    const tx = newKey();
    this.consoleTxs.push({ tx, creator, creates: issue.run !== null ? 2 : 1, deletes: issue.replaces && !edit.keepReplaced ? 1 : 0 });
    return { tx, run: runKey, listing: listingKey };
  }

  private listingRow(l: StoredListing): ListingRow {
    const v = l.spec.values;
    return {
      key: l.key,
      creator: l.creator,
      expiresAt: this.expiryOf(l.key, l.spec),
      run: l.run,
      game: v.game,
      season: v.season,
      frames: BigInt(v.frames),
      log_h: v.log_h,
      price: v.price,
      seller: v.seller,
      ...(v.book !== undefined ? { book: v.book } : {}),
      ...(v.label !== undefined ? { label: v.label } : {}),
      human: v.human,
      ...(v.pay_to !== undefined ? { pay_to: v.pay_to } : {}),
      ...(v.hcs !== undefined ? { hcs: v.hcs } : {}),
    };
  }

  async liveListingFor(runKey: string, owner: string): Promise<ListingRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const l = this.listings.find((x) => x.live && same(x.creator, owner) && x.run === runKey);
    return l ? this.listingRow(l) : null;
  }

  private stampOfRun(runKey: string): StampRow | null {
    const s = this.liveStamps().find((x) => same(x.spec.values.run, runKey));
    return s ? this.stampRow(s) : null;
  }

  async getListing(listingKey: string): Promise<ListingRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const l = this.listings.find((x) => x.live && x.key === listingKey.toLowerCase());
    if (!l) return null;
    const st = this.stampOfRun(l.run);
    const row = this.listingRow(l);
    return st && listingMismatch(st, row) === null ? row : null;
  }

  /** A listing as any wallet might write it (default: the run's own wallet), for a run already here. */
  addListing(run: string, values: ListingValues, creator?: string): string {
    const key = newKey();
    const by = (creator ?? this.runs.find((r) => r.key === run)?.creator ?? WALLET_A).toLowerCase();
    this.listings.push({ key, creator: by, run, live: true, spec: { values, flags: { readonly: true, permissionlessExtension: false }, expiry: { kind: "days", days: 7 } } });
    return key;
  }

  async getRun(runKey: string, withLog: boolean): Promise<StampedRun | null> {
    if (this.readsDown) throw new ArkivError("down");
    const st = this.stampOfRun(runKey);
    if (!st) return null;
    const r = this.runs.find((x) => x.live && x.key === runKey.toLowerCase() && same(x.creator, st.console));
    if (!r) return null;
    const row = this.runRow(r, withLog);
    return runMismatch(st, row) === null ? stamped(st, row) : null;
  }

  private async gate(): Promise<void> {
    if (this.holdWrites) await this.holdWrites;
    if (this.failWrites > 0) {
      this.failWrites -= 1;
      throw new ArkivError("reverted");
    }
  }

  async writeRunAndListing(run: CreateSpec<RunValues>, listing: CreateSpec<ListingValues>) {
    await this.gate();
    const runKey = newKey();
    const listingKey = newKey();
    this.runs.push({ key: runKey, creator: CHECKER, spec: run, live: true });
    this.listings.push({ key: listingKey, creator: CHECKER, run: runKey, spec: listing, live: true });
    const tx = newKey();
    this.batches.push({ kind: "run+listing", tx, creator: CHECKER });
    return { run: runKey, listing: listingKey, tx };
  }

  async writeHouse(pairs: HousePair[]) {
    await this.gate();
    if (!this.house) throw new ArkivError("no house key configured (HOUSE_ARKIV_KEY)");
    if (2 * pairs.length > this.maxCreates) throw new ArkivError("exceeds the block gas limit");
    const runs: string[] = [];
    const listings: string[] = [];
    for (const p of pairs) {
      const runKey = newKey();
      const listingKey = newKey();
      this.runs.push({ key: runKey, creator: this.house, spec: p.run, live: true });
      this.listings.push({ key: listingKey, creator: this.house, run: runKey, spec: p.listing, live: true });
      runs.push(runKey);
      listings.push(listingKey);
    }
    const tx = newKey();
    this.batches.push({ kind: "house", tx, creates: 2 * pairs.length, creator: this.house });
    return { runs, listings, tx };
  }

  /** The board as the real port reads it: the checker's stamps, fastest first, joined (board.ts). */
  private board(game: string, season: number) {
    const stamps = this.liveStamps()
      .filter((s) => s.spec.values.game === game && s.spec.values.season === season)
      .sort((a, b) => a.spec.values.frames - b.spec.values.frames)
      .map((s) => this.stampRow(s));
    const runs = this.runs.filter((r) => r.live && r.spec.values.game === game).map((r) => this.runRow(r, false));
    const listings = this.listings
      .filter((l) => l.live && l.spec.values.game === game && l.spec.values.season === season)
      .sort((a, b) => a.spec.values.frames - b.spec.values.frames)
      .map((l) => this.listingRow(l));
    return joinBoard(stamps, runs, listings);
  }

  async boardRuns(game: string, season: number): Promise<StampedRun[]> {
    if (this.readsDown) throw new ArkivError("down");
    return this.board(game, season).runs;
  }

  async boardListings(game: string, season: number): Promise<ListingRow[]> {
    if (this.readsDown) throw new ArkivError("down");
    return this.board(game, season).listings;
  }
}

/** A replay tool that answers what the test says (default: the log replays to `frames`). */
export class FakeChecker implements CheckerPort {
  calls = 0;
  result: Partial<ReplayResult> | "error" | "timeout" = {};

  constructor(public frames = 6170) {}

  /** The replay's final hash (arcade_splits must report the same one). */
  finalHash = 576543229;
  /** Per log hash: what the tool answers instead (house batches replay several logs). */
  byLog = new Map<string, Partial<ReplayResult>>();

  async replay(game: string, logH?: string): Promise<ReplayResult> {
    this.calls += 1;
    if (this.result === "error") throw new CheckerError("exit 2");
    if (this.result === "timeout") throw new CheckerError("timed out");
    const per = logH !== undefined ? this.byLog.get(logH) : undefined;
    return { game, hash_matches: true, complete: true, claims_match: true, finished: true, time_frames: this.frames, final_hash: this.finalHash, ...this.result, ...per };
  }

  async toolTag(): Promise<string> {
    return "arcade_replay sha256:a992006e6280";
  }
}

/** A plain .acl log: the 32-byte header (ACL1, game, rules, seed, frames, hash, score, trophies) and some inputs. */
export function makeLog(game = "MDGP", rules = 4, frames = 6461, extra = 64, seed = 1): Uint8Array {
  const b = Buffer.alloc(32 + extra);
  b.write("ACL1", 0, "latin1");
  b.write(game, 4, "latin1");
  b.writeUInt32LE(rules, 8);
  b.writeUInt32LE(seed, 12);
  b.writeUInt32LE(frames, 16);
  b.writeUInt32LE(0xcafebabe, 20);
  for (let i = 32; i < b.length; i++) b[i] = (i * 7 + seed) & 0xff;
  return Uint8Array.from(b);
}

let tags = 0;
/**
 * A console bound to `book` with `wallet` approved, as an approved link leaves it (consoles.ts).
 * Returns its store key.
 */
export function linkWallet(store: Store, book: string, wallet: string = WALLET_A): string {
  tags += 1;
  const key = randomBytes(32).toString("hex");
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
  const tag = `C-${[0, 1, 2, 3].map((i) => alphabet[Math.floor(tags / alphabet.length ** i) % alphabet.length]).join("")}`;
  const nowS = Math.floor(Date.now() / 1000);
  store.registerConsole(key, tag, nowS);
  store.setConsole(key, { book, state: "bound", by: "link", wallet: wallet.toLowerCase() }, nowS);
  return key;
}

/**
 * The console's half of one publish job: wait for the sign stage (or done), write what it issued
 * from `wallet`, report it with `written`, and wait for done. `report` changes what the console
 * tells the bridge.
 */
export async function consoleFinish(
  pub: Publisher,
  arkiv: FakeArkiv,
  id: string,
  wallet: string = WALLET_A,
  opts: { edit?: Parameters<FakeArkiv["consoleWrite"]>[2]; report?: (w: { tx: string; run: string; listing: string }) => Record<string, unknown> } = {},
): Promise<PublishView> {
  await waitFor(() => pub.view(id)?.stage === "sign" || pub.view(id)?.stage === "done");
  const v = pub.view(id)!;
  if (v.stage === "sign") {
    const w = arkiv.consoleWrite(wallet, v.data.issue as Issue, opts.edit);
    pub.written(id, opts.report ? opts.report(w) : w);
    await waitFor(() => pub.view(id)?.stage === "done");
  }
  return pub.view(id)!;
}
