/**
 * An in-memory Arkiv behind the ArkivPort interface, and a scripted checker, for the publish and
 * ghost tests. Rows are kept with the values, flags and expiry they were written with, so tests can
 * assert every column. Nothing here touches the network.
 */
import { createHash } from "node:crypto";
import type { ArkivPort, CreateSpec, HousePair, ListingRow, ListingValues, RunRow, RunValues } from "../src/arkiv/client.js";
import { ArkivError } from "../src/arkiv/client.js";
import { splitsOf } from "../src/arkiv/rows.js";
import { CheckerError, type CheckerPort, type ReplayResult } from "../src/arkiv/checker.js";

export const CHECKER = "0x1111111111111111111111111111111111111111";
export const STRANGER = "0x2222222222222222222222222222222222222222";

export interface StoredRun {
  key: string;
  creator: string;
  spec: CreateSpec<RunValues>;
  live: boolean;
}
export interface StoredListing {
  key: string;
  creator: string;
  run: string;
  spec: CreateSpec<ListingValues>;
  live: boolean;
}

let counter = 0;
function newKey(): string {
  counter += 1;
  return `0x${createHash("sha256").update(`key-${counter}`).digest("hex")}`;
}

export class FakeArkiv implements ArkivPort {
  runs: StoredRun[] = [];
  listings: StoredListing[] = [];
  batches: { kind: "run+listing" | "listing" | "run" | "house"; tx: string; creates?: number }[] = [];
  /** A house transaction with more creates than this is refused (gas or size), as Arkiv would. */
  maxCreates = Infinity;
  chain = 7794095;
  balances = new Map<string, bigint>([[CHECKER.toLowerCase(), 10n ** 18n]]);
  /** Throw on the next n writes (Arkiv down, a revert). */
  failWrites = 0;
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

  /** A run as any wallet might write it (look-alikes, open-tier rows). */
  addRun(values: RunValues, creator = CHECKER): string {
    const key = newKey();
    this.runs.push({ key, creator, live: true, spec: { values, flags: { readonly: true, permissionlessExtension: true }, expiry: { kind: "days", days: 30 } } });
    return key;
  }

  private runRow(r: StoredRun, withLog: boolean): RunRow {
    const v = r.spec.values;
    return {
      key: r.key,
      creator: r.creator,
      expiresAt: 1000n,
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
      ...(() => {
        const splits = splitsOf({
          frames: BigInt(v.frames),
          ...(v.s1 !== undefined ? { s1: BigInt(v.s1) } : {}),
          ...(v.s2 !== undefined ? { s2: BigInt(v.s2) } : {}),
          ...(v.s3 !== undefined ? { s3: BigInt(v.s3) } : {}),
          ...(v.s4 !== undefined ? { s4: BigInt(v.s4) } : {}),
          ...(v.split_kind !== undefined ? { split_kind: v.split_kind } : {}),
        });
        return splits ? { splits } : {};
      })(),
    };
  }

  async runByLogHash(logH: string): Promise<RunRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const r = this.runs.find((x) => x.live && x.creator === CHECKER && x.spec.values.log_h === logH);
    return r ? this.runRow(r, false) : null;
  }

  private listingRow(l: StoredListing): ListingRow {
    const v = l.spec.values;
    return {
      key: l.key,
      creator: l.creator,
      expiresAt: 500n,
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

  async liveListingFor(runKey: string): Promise<ListingRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const l = this.listings.find((x) => x.live && x.creator === CHECKER && x.run === runKey);
    return l ? this.listingRow(l) : null;
  }

  async getListing(listingKey: string): Promise<ListingRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const l = this.listings.find((x) => x.live && x.creator === CHECKER && x.key === listingKey.toLowerCase());
    return l ? this.listingRow(l) : null;
  }

  /** A listing as any wallet might write it, for a run already here. */
  addListing(run: string, values: ListingValues, creator = CHECKER): string {
    const key = newKey();
    this.listings.push({ key, creator, run, live: true, spec: { values, flags: { readonly: true, permissionlessExtension: false }, expiry: { kind: "days", days: 7 } } });
    return key;
  }

  async getRun(runKey: string, withLog: boolean): Promise<RunRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const r = this.runs.find((x) => x.live && x.creator === CHECKER && x.key === runKey.toLowerCase());
    return r ? this.runRow(r, withLog) : null;
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
    this.batches.push({ kind: "run+listing", tx });
    return { run: runKey, listing: listingKey, tx };
  }

  async writeListing(runKey: string, listing: CreateSpec<ListingValues>, replaces?: string) {
    await this.gate();
    if (replaces) {
      const old = this.listings.find((x) => x.key === replaces);
      if (old) old.live = false;
    }
    const listingKey = newKey();
    this.listings.push({ key: listingKey, creator: CHECKER, run: runKey, spec: listing, live: true });
    const tx = newKey();
    this.batches.push({ kind: "listing", tx });
    return { listing: listingKey, tx };
  }

  async writeHouse(pairs: HousePair[]) {
    await this.gate();
    if (2 * pairs.length > this.maxCreates) throw new ArkivError("exceeds the block gas limit");
    const runs: string[] = [];
    const listings: string[] = [];
    for (const p of pairs) {
      const runKey = newKey();
      const listingKey = newKey();
      this.runs.push({ key: runKey, creator: CHECKER, spec: p.run, live: true });
      this.listings.push({ key: listingKey, creator: CHECKER, run: runKey, spec: p.listing, live: true });
      runs.push(runKey);
      listings.push(listingKey);
    }
    const tx = newKey();
    this.batches.push({ kind: "house", tx, creates: 2 * pairs.length });
    return { runs, listings, tx };
  }

  async boardRuns(game: string, season: number): Promise<RunRow[]> {
    if (this.readsDown) throw new ArkivError("down");
    return this.runs
      .filter((r) => r.live && r.creator === CHECKER && r.spec.values.game === game && r.spec.values.season === season)
      .sort((a, b) => a.spec.values.frames - b.spec.values.frames)
      .map((r) => this.runRow(r, false));
  }

  async boardListings(game: string, season: number): Promise<ListingRow[]> {
    if (this.readsDown) throw new ArkivError("down");
    return this.listings
      .filter((l) => l.live && l.creator === CHECKER && l.spec.values.game === game && l.spec.values.season === season)
      .sort((a, b) => a.spec.values.frames - b.spec.values.frames)
      .map((l) => this.listingRow(l));
  }

  async writeRun(run: CreateSpec<RunValues>) {
    await this.gate();
    const runKey = newKey();
    this.runs.push({ key: runKey, creator: CHECKER, spec: run, live: true });
    const tx = newKey();
    this.batches.push({ kind: "run", tx });
    return { run: runKey, tx };
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
