/**
 * The readers' rule (spec: Entities, console-owned records), as one pure join every bridge reader
 * goes through (boardRuns, boardListings, getRun, getListing) and the web board mirrors line for
 * line in browser JS (public/board.html `joinBoard`; a test runs both on the same rows).
 *
 * A run counts only when a stamp the checker created names it, the run's creator and its current
 * owner are both the wallet the stamp names as its `console` (a readonly entity can still be
 * transferred, so the owner is read too: a missing owner counts as a mismatch), and the columns the
 * stamp copied agree with the run's: game, season, frames, log_h, book or label, human and the lap
 * splits. Any
 * mismatch drops the stamp and its run. Two stamps of one log (or of one run) count once: the
 * first, which on a board read is the fastest.
 *
 * A listing counts only when its creator and owner are that same console, its `run` names a run that counted,
 * and its game, season, frames, log_h, book or label and human are the run's. A stamped run whose
 * listing expired still counts, as not for sale.
 *
 * The stamps a reader passes in must already be pinned to the checker (the raw readers drop any
 * other creator); the runs and listings may come from any wallet, the join checks their creator.
 */
import type { ListingRow, RunRow, StampedRun, StampRow } from "./client.js";

const ADDRESS_RE = /^0x[0-9a-f]{40}$/;

const sameSplits = (a: readonly number[] | undefined, b: readonly number[] | undefined) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** Why this run does not count under this stamp, or null when it does. */
export function runMismatch(st: StampRow, r: RunRow): string | null {
  if (!ADDRESS_RE.test(st.console)) return "the stamp names no wallet";
  if (r.key.toLowerCase() !== st.run.toLowerCase()) return "another run";
  if ((r.creator ?? "").toLowerCase() !== st.console) return "created by another wallet than the stamp names";
  if ((r.owner ?? "").toLowerCase() !== st.console) return "owned by another wallet than the stamp names";
  if (r.game !== st.game) return "game";
  if (r.season !== st.season) return "season";
  if (r.frames !== st.frames) return "frames";
  if (r.log_h !== st.log_h) return "log_h";
  if ((r.book ?? null) !== (st.book ?? null)) return "book";
  if ((r.label ?? null) !== (st.label ?? null)) return "label";
  if (r.human !== st.human) return "human";
  if (!sameSplits(r.splits, st.splits)) return "splits";
  return null;
}

/** Why this listing does not count for this stamped run, or null when it does. */
export function listingMismatch(st: StampRow, l: ListingRow): string | null {
  if (l.run.toLowerCase() !== st.run.toLowerCase()) return "another run";
  if ((l.creator ?? "").toLowerCase() !== st.console) return "created by another wallet than the run's";
  if ((l.owner ?? "").toLowerCase() !== st.console) return "owned by another wallet than the run's";
  if (l.game !== st.game) return "game";
  if (l.season !== st.season) return "season";
  if (l.frames !== st.frames) return "frames";
  if (l.log_h !== st.log_h) return "log_h";
  if ((l.book ?? null) !== (st.book ?? null)) return "book";
  if ((l.label ?? null) !== (st.label ?? null)) return "label";
  if (l.human !== st.human) return "human";
  return null;
}

/** A run that counted, as the readers hand it on: its owner (the stamp's console) and its stamp's key. */
export function stamped(st: StampRow, r: RunRow): StampedRun {
  return { ...r, owner: st.console, stamp: st.key };
}

export interface Joined {
  /** The runs that counted, in the stamps' order (fastest first on a board read). */
  runs: StampedRun[];
  /** The listings that counted, in the order given. */
  listings: ListingRow[];
  /** Stamps and listings that did not count, and why (a log line, a board's note). */
  dropped: number;
  why: string[];
}

/** The board: every stamp joined to its run, then every listing to its stamped run. */
export function joinBoard(stamps: readonly StampRow[], runs: readonly RunRow[], listings: readonly ListingRow[]): Joined {
  const byKey = new Map(runs.map((r) => [r.key.toLowerCase(), r]));
  const out: StampedRun[] = [];
  const stampOf = new Map<string, StampRow>();
  const seenLog = new Set<string>();
  const why: string[] = [];
  for (const st of stamps) {
    const runKey = st.run.toLowerCase();
    if (seenLog.has(st.log_h) || stampOf.has(runKey)) {
      why.push(`stamp ${st.key}: another stamp of the same log counts`);
      continue;
    }
    const r = byKey.get(runKey);
    const off = r ? runMismatch(st, r) : "its run is not on Arkiv";
    if (off !== null || !r) {
      why.push(`stamp ${st.key}: ${off}`);
      continue;
    }
    seenLog.add(st.log_h);
    stampOf.set(runKey, st);
    out.push(stamped(st, r));
  }
  const kept: ListingRow[] = [];
  for (const l of listings) {
    const st = stampOf.get(l.run.toLowerCase());
    const off = st ? listingMismatch(st, l) : "its run is not a stamped run";
    if (off !== null || !st) {
      why.push(`listing ${l.key}: ${off}`);
      continue;
    }
    kept.push(l);
  }
  return { runs: out, listings: kept, dropped: why.length, why };
}
