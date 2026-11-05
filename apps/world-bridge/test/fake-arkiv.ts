/**
 * An in-memory Arkiv behind the ArkivPort interface, and a scripted checker, for the publish and
 * ghost tests. Rows are kept with the values, flags and expiry they were written with, so tests can
 * assert every column. Nothing here touches the network.
 */
import { createHash } from "node:crypto";
import type { ArkivPort, CreateSpec, ListingRow, ListingValues, RunRow, RunValues } from "../src/arkiv/client.js";
import { ArkivError } from "../src/arkiv/client.js";
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
  batches: { kind: "run+listing" | "listing" | "run"; tx: string }[] = [];
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
    };
  }

  async runByLogHash(logH: string): Promise<RunRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const r = this.runs.find((x) => x.live && x.creator === CHECKER && x.spec.values.log_h === logH);
    return r ? this.runRow(r, false) : null;
  }

  async liveListingFor(runKey: string): Promise<ListingRow | null> {
    if (this.readsDown) throw new ArkivError("down");
    const l = this.listings.find((x) => x.live && x.creator === CHECKER && x.run === runKey);
    if (!l) return null;
    const v = l.spec.values;
    return { key: l.key, creator: l.creator, expiresAt: 500n, run: l.run, game: v.game, season: v.season, frames: BigInt(v.frames), log_h: v.log_h, price: v.price, seller: v.seller, book: v.book, human: v.human };
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

  async writeListing(runKey: string, listing: CreateSpec<ListingValues>) {
    await this.gate();
    const listingKey = newKey();
    this.listings.push({ key: listingKey, creator: CHECKER, run: runKey, spec: listing, live: true });
    const tx = newKey();
    this.batches.push({ kind: "listing", tx });
    return { listing: listingKey, tx };
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

  async replay(game: string): Promise<ReplayResult> {
    this.calls += 1;
    if (this.result === "error") throw new CheckerError("exit 2");
    if (this.result === "timeout") throw new CheckerError("timed out");
    return { game, hash_matches: true, complete: true, claims_match: true, finished: true, time_frames: this.frames, ...this.result };
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
